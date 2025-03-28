# Generated by Django 5.1.2 on 2024-10-28 00:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_account_archived'),
    ]

    operations = [
        migrations.RenameField(
            model_name='account',
            old_name='archived',
            new_name='is_archived',
        ),
        migrations.AlterField(
            model_name='account',
            name='is_asset',
            field=models.BooleanField(default=False, help_text='Asset accounts count towards your Net Worth, but not towards your month.', verbose_name='Asset account'),
        ),
    ]
