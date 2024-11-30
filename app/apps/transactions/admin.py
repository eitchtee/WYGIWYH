from django.contrib import admin

from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    RecurringTransaction,
    TransactionEntity,
)


@admin.register(Transaction)
class TransactionModelAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "type",
        "account__name",
        "amount",
        "account__currency__code",
        "date",
        "reference_date",
    ]


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


admin.site.register(TransactionCategory)
admin.site.register(TransactionTag)
admin.site.register(TransactionEntity)
