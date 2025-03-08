from import_export import resources, fields
from django.contrib.auth import get_user_model
from django.conf import settings


from apps.users.models import UserSettings

User = get_user_model()


class UserResource(resources.ModelResource):
    # User fields
    email = fields.Field(attribute="email", column_name="Email")

    # UserSettings fields - for export only
    hide_amounts = fields.Field(
        attribute="settings__hide_amounts", column_name="Hide Amounts", readonly=True
    )
    mute_sounds = fields.Field(
        attribute="settings__mute_sounds", column_name="Mute Sounds", readonly=True
    )
    date_format = fields.Field(
        attribute="settings__date_format", column_name="Date Format", readonly=True
    )
    datetime_format = fields.Field(
        attribute="settings__datetime_format",
        column_name="Datetime Format",
        readonly=True,
    )
    number_format = fields.Field(
        attribute="settings__number_format", column_name="Number Format", readonly=True
    )
    language = fields.Field(
        attribute="settings__language", column_name="Language", readonly=True
    )
    timezone = fields.Field(
        attribute="settings__timezone", column_name="Timezone", readonly=True
    )
    start_page = fields.Field(
        attribute="settings__start_page", column_name="Start Page", readonly=True
    )

    # Human-readable fields for choice values
    start_page_display = fields.Field(column_name="Start Page Display", readonly=True)
    language_display = fields.Field(column_name="Language Display", readonly=True)
    timezone_display = fields.Field(column_name="Timezone Display", readonly=True)

    @staticmethod
    def dehydrate_start_page_display(user):
        if hasattr(user, "settings"):
            return dict(UserSettings.StartPage.choices).get(
                user.settings.start_page, ""
            )
        return ""

    @staticmethod
    def dehydrate_language_display(user):
        if hasattr(user, "settings"):
            languages = dict([("auto", "Auto")] + list(settings.LANGUAGES))
            return languages.get(user.settings.language, user.settings.language)
        return ""

    @staticmethod
    def dehydrate_timezone_display(user):
        if hasattr(user, "settings"):
            if user.settings.timezone == "auto":
                return "Auto"
            return user.settings.timezone
        return ""

    def after_init_instance(self, instance, new, row, **kwargs):
        """
        Store settings data on the instance to be used after save
        """
        # Process boolean fields properly
        hide_amounts = row.get("Hide Amounts", "").lower() == "true"
        mute_sounds = row.get("Mute Sounds", "").lower() == "true"

        # Store settings data on the instance for later use
        instance._settings_data = {
            "hide_amounts": hide_amounts,
            "mute_sounds": mute_sounds,
            "date_format": row.get("Date Format", "SHORT_DATE_FORMAT"),
            "datetime_format": row.get("Datetime Format", "SHORT_DATETIME_FORMAT"),
            "number_format": row.get("Number Format", "AA"),
            "language": row.get("Language", "auto"),
            "timezone": row.get("Timezone", "auto"),
            "start_page": row.get("Start Page", UserSettings.StartPage.MONTHLY),
        }

        return instance

    def after_save_instance(self, instance, row, **kwargs):
        """
        Create or update UserSettings after User is saved
        """
        if not hasattr(instance, "_settings_data"):
            return

        settings_data = instance._settings_data

        # Create or update UserSettings
        try:
            user_settings = UserSettings.objects.get(user=instance)
            # Update existing settings
            for key, value in settings_data.items():
                setattr(user_settings, key, value)
            user_settings.save()
        except UserSettings.DoesNotExist:
            # Create new settings
            UserSettings.objects.create(user=instance, **settings_data)

    def get_queryset(self):
        """
        Ensure settings are prefetched when exporting users
        """
        return super().get_queryset().select_related("settings")

    class Meta:
        model = User
        import_id_fields = ["id"]
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "password",
            "hide_amounts",
            "mute_sounds",
            "date_format",
            "datetime_format",
            "number_format",
            "language",
            "language_display",
            "timezone",
            "timezone_display",
            "start_page",
            "start_page_display",
        )
        export_order = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "password",
            "hide_amounts",
            "mute_sounds",
            "date_format",
            "datetime_format",
            "number_format",
            "language",
            "language_display",
            "timezone",
            "timezone_display",
            "start_page",
            "start_page_display",
        )
