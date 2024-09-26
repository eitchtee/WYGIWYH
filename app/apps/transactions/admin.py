from django.contrib import admin

from apps.transactions.models import Transaction, TransactionCategory, TransactionTag


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


admin.site.register(TransactionCategory)
admin.site.register(TransactionTag)
