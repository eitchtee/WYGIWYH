# Generated by Django 5.1.7 on 2025-03-09 20:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0040_alter_transaction_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='installmentplan',
            name='add_description_to_transaction',
            field=models.BooleanField(default=True, verbose_name='Add description to transactions'),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='add_notes_to_transaction',
            field=models.BooleanField(default=True, verbose_name='Add notes to transactions'),
        ),
        migrations.AddField(
            model_name='recurringtransaction',
            name='add_description_to_transaction',
            field=models.BooleanField(default=True, verbose_name='Add description to transactions'),
        ),
        migrations.AddField(
            model_name='recurringtransaction',
            name='add_notes_to_transaction',
            field=models.BooleanField(default=True, verbose_name='Add notes to transactions'),
        ),
    ]
