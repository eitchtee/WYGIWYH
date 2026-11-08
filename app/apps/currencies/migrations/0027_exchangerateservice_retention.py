import django.core.validators
from django.db import migrations, models


def singleton_to_max_rates(apps, schema_editor):
    Service = apps.get_model("currencies", "ExchangeRateService")
    Service.objects.filter(singleton=True).update(max_rates=1)


def max_rates_to_singleton(apps, schema_editor):
    Service = apps.get_model("currencies", "ExchangeRateService")
    Service.objects.filter(max_rates=1).update(singleton=True)


class Migration(migrations.Migration):
    dependencies = [
        ("currencies", "0026_exchangerateservice_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="exchangerateservice",
            name="one_per_day",
            field=models.BooleanField(
                default=False,
                help_text="Update the day's exchange rate on each fetch instead of adding a new one.",
                verbose_name="One exchange rate per day",
            ),
        ),
        migrations.AddField(
            model_name="exchangerateservice",
            name="max_rates",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                help_text="Keep at most this many automatic exchange rates per currency pair, deleting the oldest first. Leave empty to keep all.",
                verbose_name="Exchange rates to keep",
            ),
        ),
        migrations.RunPython(singleton_to_max_rates, max_rates_to_singleton),
        migrations.RemoveField(model_name="exchangerateservice", name="singleton"),
    ]
