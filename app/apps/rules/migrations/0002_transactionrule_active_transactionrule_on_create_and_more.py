# Generated by Django 5.1.2 on 2024-10-22 17:52

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='transactionrule',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='transactionrule',
            name='on_create',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='transactionrule',
            name='on_update',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='transactionruleaction',
            name='rule',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='rules.transactionrule', verbose_name='Rule'),
        ),
        migrations.AlterField(
            model_name='transactionruleaction',
            name='value',
            field=models.TextField(verbose_name='Value'),
        ),
    ]