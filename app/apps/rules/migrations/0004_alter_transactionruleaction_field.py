# Generated by Django 5.1.3 on 2024-11-30 20:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0003_alter_transactionruleaction_unique_together'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transactionruleaction',
            name='field',
            field=models.CharField(choices=[('account', 'Account'), ('type', 'Type'), ('is_paid', 'Paid'), ('date', 'Date'), ('reference_date', 'Reference Date'), ('amount', 'Amount'), ('description', 'Description'), ('notes', 'Notes'), ('category', 'Category'), ('tags', 'Tags'), ('entities', 'Entities')], max_length=50, verbose_name='Field'),
        ),
    ]
