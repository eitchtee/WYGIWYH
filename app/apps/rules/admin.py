from django.contrib import admin

from apps.rules.models import TransactionRule, TransactionRuleAction

# Register your models here.
admin.site.register(TransactionRule)
admin.site.register(TransactionRuleAction)
