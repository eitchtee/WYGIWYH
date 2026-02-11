from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_account_untracked_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='is_default',
            field=models.BooleanField(default=False, help_text="Use as a default account when adding new transactions", verbose_name='Default'),
        ),
    ]
