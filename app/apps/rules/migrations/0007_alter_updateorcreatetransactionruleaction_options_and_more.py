# Generated by Django 5.1.5 on 2025-02-08 04:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0006_updateorcreatetransactionruleaction'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='updateorcreatetransactionruleaction',
            options={'verbose_name': 'Update or Create Transaction Action', 'verbose_name_plural': 'Update or Create Transaction Action Actions'},
        ),
        migrations.AddField(
            model_name='updateorcreatetransactionruleaction',
            name='filter',
            field=models.TextField(blank=True, help_text='Generic expression to enable or disable execution. Should evaluate to True or False', verbose_name='Filter'),
        ),
    ]
