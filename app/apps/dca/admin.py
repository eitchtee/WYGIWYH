from django.contrib import admin

from apps.dca.models import DCAStrategy, DCAEntry

# Register your models here.
admin.site.register(DCAStrategy)
admin.site.register(DCAEntry)
