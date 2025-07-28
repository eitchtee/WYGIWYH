from django.contrib import admin
from django.utils.translation import gettext_lazy as _


@admin.action(description=_("Make public"))
def make_public(modeladmin, request, queryset):
    queryset.update(visibility="public")


@admin.action(description=_("Make private"))
def make_private(modeladmin, request, queryset):
    queryset.update(visibility="private")


class SharedObjectModelAdmin(admin.ModelAdmin):
    actions = [make_public, make_private]

    list_display = ("__str__", "visibility", "owner", "get_shared_with")

    @admin.display(description=_("Shared with users"))
    def get_shared_with(self, obj):
        return ", ".join([p.email for p in obj.shared_with.all()])

    def get_queryset(self, request):
        # Use the all_objects manager to show all transactions, including deleted ones
        return self.model.all_objects.all()
