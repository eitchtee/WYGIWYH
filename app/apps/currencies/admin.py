from django.contrib import admin

from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "suffix" or db_field.name == "prefix":
            kwargs["strip"] = False
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(ExchangeRateService)
class ExchangeRateServiceAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "service_type",
        "is_active",
        "interval_type",
        "fetch_interval",
        "last_fetch",
    ]
    list_filter = ["is_active", "service_type"]
    search_fields = ["name"]
    filter_horizontal = ["target_currencies"]


admin.site.register(ExchangeRate)
