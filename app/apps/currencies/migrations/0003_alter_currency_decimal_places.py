# Generated by Django 5.1.1 on 2024-09-23 04:05

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('currencies', '0002_currency_prefix_currency_suffix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='currency',
            name='decimal_places',
            field=models.PositiveIntegerField(default=2, validators=[django.core.validators.MaxValueValidator(30), django.core.validators.MinValueValidator(0)], verbose_name='Decimal Places'),
        ),
    ]
