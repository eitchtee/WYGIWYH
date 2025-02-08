from django.contrib import admin

from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)


admin.site.register(TransactionRule)
admin.site.register(TransactionRuleAction)
admin.site.register(UpdateOrCreateTransactionRuleAction)
