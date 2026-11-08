from django.db import migrations


def link_entry_transactions(apps, schema_editor):
    """Joins each DCA entry's expense and income into a transfer, so investment
    tracking sees the purchase. Mirrors Transaction.transfer_link_error()."""
    DCAEntry = apps.get_model("dca", "DCAEntry")
    Transaction = apps.get_model("transactions", "Transaction")

    entries = DCAEntry.objects.filter(
        expense_transaction__isnull=False, income_transaction__isnull=False
    ).select_related("expense_transaction", "income_transaction")
    for entry in entries:
        expense, income = entry.expense_transaction, entry.income_transaction
        if (
            expense.type != "EX"
            or income.type != "IN"
            or expense.account_id == income.account_id
            or expense.linked_transaction_id
            or income.linked_transaction_id
            # a legacy one-way link already points at one of them
            or Transaction.objects.filter(
                linked_transaction_id__in=(expense.pk, income.pk)
            ).exists()
        ):
            continue
        Transaction.objects.filter(pk=expense.pk).update(linked_transaction=income)
        Transaction.objects.filter(pk=income.pk).update(linked_transaction=expense)


class Migration(migrations.Migration):
    dependencies = [
        ("dca", "0004_alter_dcastrategy_owner_and_more"),
        ("transactions", "0052_transfer_templates"),
    ]

    operations = [
        migrations.RunPython(link_entry_transactions, migrations.RunPython.noop),
    ]
