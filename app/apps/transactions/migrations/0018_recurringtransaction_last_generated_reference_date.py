# Generated by Django 5.1.2 on 2024-10-17 02:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0017_recurringtransaction_reference_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurringtransaction',
            name='last_generated_reference_date',
            field=models.DateField(blank=True, null=True, verbose_name='Last Generated Reference Date'),
        ),
    ]