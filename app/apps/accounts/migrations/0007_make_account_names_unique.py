from django.db import migrations, models


def make_names_unique(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")

    # Get all accounts ordered by id
    accounts = Account.objects.all().order_by("id")

    # Track seen names
    seen_names = {}

    for account in accounts:
        original_name = account.name
        counter = seen_names.get(original_name, 0)

        while account.name in seen_names:
            counter += 1
            account.name = f"{original_name} ({counter})"

        seen_names[account.name] = counter
        account.save()


def reverse_migration(apps, schema_editor):
    # Can't restore original names, so do nothing
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_rename_archived_account_is_archived_and_more"),
    ]

    operations = [
        migrations.RunPython(make_names_unique, reverse_migration),
    ]
