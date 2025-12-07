from rest_framework import serializers

from apps.import_app.models import ImportProfile, ImportRun


class ImportProfileSerializer(serializers.ModelSerializer):
    """Serializer for listing import profiles."""

    class Meta:
        model = ImportProfile
        fields = ["id", "name", "version", "yaml_config"]


class ImportRunSerializer(serializers.ModelSerializer):
    """Serializer for listing import runs."""

    class Meta:
        model = ImportRun
        fields = [
            "id",
            "status",
            "profile",
            "file_name",
            "logs",
            "processed_rows",
            "total_rows",
            "successful_rows",
            "skipped_rows",
            "failed_rows",
            "started_at",
            "finished_at",
        ]


class ImportFileSerializer(serializers.Serializer):
    """Serializer for uploading a file to import using an existing profile."""

    profile_id = serializers.PrimaryKeyRelatedField(
        queryset=ImportProfile.objects.all(), source="profile"
    )
    file = serializers.FileField()
