from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import Account
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
            "account",
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
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(is_archived=False),
        source="account",
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reload the querysets to get an updated version with the requesting user
        self.fields["profile_id"].queryset = ImportProfile.objects.all()
        self.fields["account_id"].queryset = Account.objects.filter(is_archived=False)

    def validate(self, data):
        if data.get("account") and not data["profile"].imports_transactions:
            raise serializers.ValidationError(
                {"account_id": _("Only transaction imports can use an account.")}
            )
        return data
