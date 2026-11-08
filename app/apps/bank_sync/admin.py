from django.contrib import admin

from apps.bank_sync.models import BankSyncAccount, BankSyncService

admin.site.register(BankSyncService)
admin.site.register(BankSyncAccount)
