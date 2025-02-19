from import_export import fields


class EmptyStringToNoneField(fields.Field):
    def clean(self, data, **kwargs):
        value = super().clean(data)
        return None if value == "" else value
