from django.contrib.admin import ModelAdmin
from django.contrib.auth.forms import (
    UserChangeForm,
    UserCreationForm,
    AdminPasswordChangeForm,
)
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from apps.users.models import User, UserSettings

admin.site.unregister(Group)


class UserSettingsInline(admin.StackedInline):
    model = UserSettings
    can_delete = False
    extra = 0
    verbose_name_plural = _("User Settings")
    verbose_name = _("User Setting")


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    ordering = ("email",)
    exclude = ("username",)
    list_display = ("email", "is_staff")
    search_fields = ("first_name", "last_name", "email")
    inlines = (UserSettingsInline,)

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                )
            },
        ),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


admin.site.register(UserSettings)
