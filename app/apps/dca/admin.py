from django.contrib import admin

from apps.dca.models import DCAStrategy, DCAEntry
from apps.common.admin import SharedObjectModelAdmin


admin.site.register(DCAEntry)


@admin.register(DCAStrategy)
class TransactionEntityModelAdmin(SharedObjectModelAdmin):
    def get_queryset(self, request):
        return DCAStrategy.all_objects.all()
