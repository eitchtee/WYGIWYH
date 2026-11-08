import django.db.models.deletion
from django.db import migrations, models


def copy_income_entity(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    for account in Account.objects.exclude(income_entity=None):
        account.income_entities.add(account.income_entity_id)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0017_account_income_entity_account_is_investment"),
        ("transactions", "0052_transfer_templates"),
    ]

    operations = [
        # Free the "investment_accounts" reverse name for the new field
        migrations.AlterField(
            model_name="account",
            name="income_entity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="transactions.transactionentity",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="income_entities",
            field=models.ManyToManyField(
                blank=True,
                help_text="Income transactions with any of these entities (dividends, interest, rent) count towards this investment's return.",
                related_name="investment_accounts",
                to="transactions.transactionentity",
                verbose_name="Income entities",
            ),
        ),
        migrations.RunPython(copy_income_entity, migrations.RunPython.noop),
        migrations.RemoveField(model_name="account", name="income_entity"),
    ]
