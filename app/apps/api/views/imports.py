from django.core.files.storage import FileSystemStorage
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.serializers import ImportFileSerializer, ImportProfileSerializer, ImportRunSerializer
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.tasks import process_import


@extend_schema_view(
    list=extend_schema(
        summary="List import profiles",
        description="Returns a paginated list of all available import profiles.",
    ),
    retrieve=extend_schema(
        summary="Get import profile",
        description="Returns the details of a specific import profile by ID.",
    ),
)
class ImportProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing and retrieving import profiles."""

    queryset = ImportProfile.objects.all()
    serializer_class = ImportProfileSerializer
    permission_classes = [IsAuthenticated]


@extend_schema_view(
    list=extend_schema(
        summary="List import runs",
        description="Returns a paginated list of import runs. Optionally filter by profile_id.",
        parameters=[
            OpenApiParameter(
                name="profile_id",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Filter runs by profile ID",
                required=False,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Get import run",
        description="Returns the details of a specific import run by ID, including status and logs.",
    ),
)
class ImportRunViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing and retrieving import runs."""

    queryset = ImportRun.objects.all().order_by("-id")
    serializer_class = ImportRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        profile_id = self.request.query_params.get("profile_id")
        if profile_id:
            queryset = queryset.filter(profile_id=profile_id)
        return queryset


@extend_schema_view(
    create=extend_schema(
        summary="Import file",
        description="Upload a CSV or XLSX file to import using an existing import profile. The import is queued and processed asynchronously.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "profile_id": {"type": "integer", "description": "ID of the ImportProfile to use"},
                    "file": {"type": "string", "format": "binary", "description": "CSV or XLSX file to import"},
                },
                "required": ["profile_id", "file"],
            },
        },
        responses={
            202: inline_serializer(
                name="ImportResponse",
                fields={
                    "import_run_id": drf_serializers.IntegerField(),
                    "status": drf_serializers.CharField(),
                },
            ),
        },
    ),
)
class ImportViewSet(viewsets.ViewSet):
    """ViewSet for importing data via file upload."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def create(self, request):
        serializer = ImportFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = serializer.validated_data["profile"]
        uploaded_file = serializer.validated_data["file"]

        # Save file to temp location
        fs = FileSystemStorage(location="/usr/src/app/temp")
        filename = fs.save(uploaded_file.name, uploaded_file)
        file_path = fs.path(filename)

        # Create ImportRun record
        import_run = ImportRun.objects.create(profile=profile, file_name=filename)

        # Queue import task
        process_import.defer(
            import_run_id=import_run.id,
            file_path=file_path,
            user_id=request.user.id,
        )

        return Response(
            {"import_run_id": import_run.id, "status": "queued"},
            status=status.HTTP_202_ACCEPTED,
        )
