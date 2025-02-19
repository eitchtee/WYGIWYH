from decimal import Decimal

from import_export.widgets import NumberWidget


class UniversalDecimalWidget(NumberWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if self.is_empty(value):
            return None
        # Replace comma with dot if present
        if isinstance(value, str):
            value = value.replace(",", ".")
        return Decimal(str(value))

    def render(self, value, obj=None, **kwargs):
        if value is None:
            return ""
        return str(value).replace(",", ".")
