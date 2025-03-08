from django.contrib import admin

from apps.accounts.models import Account, AccountGroup
from apps.common.admin import SharedObjectModelAdmin


@admin.register(Account)
class AccountModelAdmin(SharedObjectModelAdmin):
    pass


@admin.register(AccountGroup)
class AccountGroupModelAdmin(SharedObjectModelAdmin):
    pass
