# Generated by Django 5.1.1 on 2024-10-08 23:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_account_exchange_currency"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=255, unique=True, verbose_name="Name"),
                ),
            ],
            options={
                "verbose_name": "Account Group",
                "verbose_name_plural": "Account Groups",
                "db_table": "account_groups",
            },
        ),
        migrations.AlterField(
            model_name="account",
            name="name",
            field=models.CharField(max_length=255, verbose_name="Name"),
        ),
    ]
