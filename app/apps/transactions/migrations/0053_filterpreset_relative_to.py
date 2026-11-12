from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0052_transfer_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="filterpreset",
            name="relative_to",
            field=models.DateField(blank=True, null=True),
        ),
    ]
