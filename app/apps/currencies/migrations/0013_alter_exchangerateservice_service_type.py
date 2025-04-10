# Generated by Django 5.1.6 on 2025-03-02 01:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('currencies', '0012_alter_exchangerateservice_service_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exchangerateservice',
            name='service_type',
            field=models.CharField(choices=[('synth_finance', 'Synth Finance'), ('synth_finance_stock', 'Synth Finance Stock'), ('coingecko_free', 'CoinGecko (Demo/Free)'), ('coingecko_pro', 'CoinGecko (Pro)'), ('transitive', 'Transitive (Calculated from Existing Rates)')], max_length=255, verbose_name='Service Type'),
        ),
    ]
