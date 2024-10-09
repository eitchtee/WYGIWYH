from django.contrib import admin

from apps.currencies.models import Currency, ExchangeRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "suffix" or db_field.name == "prefix":
            kwargs["strip"] = False
        return super().formfield_for_dbfield(db_field, request, **kwargs)


admin.site.register(ExchangeRate)
