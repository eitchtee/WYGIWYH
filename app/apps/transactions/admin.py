from django.contrib import admin

from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    RecurringTransaction,
    TransactionEntity,
    QuickTransaction,
)
from apps.common.admin import SharedObjectModelAdmin


@admin.register(Transaction)
class TransactionModelAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Use the all_objects manager to show all transactions, including deleted ones
        return self.model.userless_all_objects.all()

    list_filter = ["deleted", "type", "is_paid", "date", "account"]

    list_display = [
        "date",
        "description",
        "type",
        "account__name",
        "amount",
        "account__currency__code",
        "reference_date",
        "deleted",
    ]
    readonly_fields = ["deleted_at"]

    actions = ["hard_delete_selected"]

    def hard_delete_selected(self, request, queryset):
        for obj in queryset:
            obj.hard_delete()
        self.message_user(
            request, f"Successfully hard deleted {queryset.count()} transactions."
        )

    hard_delete_selected.short_description = "Hard delete selected transactions"


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0


@admin.register(InstallmentPlan)
class InstallmentPlanAdmin(admin.ModelAdmin):
    inlines = [
        TransactionInline,
    ]


@admin.register(RecurringTransaction)
class RecurringTransactionAdmin(admin.ModelAdmin):
    inlines = [
        TransactionInline,
    ]


admin.site.register(QuickTransaction)


@admin.register(TransactionCategory)
class TransactionCategoryModelAdmin(SharedObjectModelAdmin):
    pass


@admin.register(TransactionTag)
class TransactionTagModelAdmin(SharedObjectModelAdmin):
    pass


@admin.register(TransactionEntity)
class TransactionEntityModelAdmin(SharedObjectModelAdmin):
    pass
