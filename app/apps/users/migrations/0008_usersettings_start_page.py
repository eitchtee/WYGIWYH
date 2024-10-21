# Generated by Django 5.1.2 on 2024-10-21 01:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_usersettings_mute_sounds'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersettings',
            name='start_page',
            field=models.CharField(choices=[('MONTHLY_OVERVIEW', 'Overview > Monthly'), ('YEARLY_OVERVIEW', 'Overview > Yearly')], default='MONTHLY_OVERVIEW', max_length=255, verbose_name='Start page'),
        ),
    ]