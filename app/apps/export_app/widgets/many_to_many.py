from import_export.widgets import ManyToManyWidget


class AutoCreateManyToManyWidget(ManyToManyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return []

        values = value.split(self.separator)
        cleaned_values = []

        for val in values:
            val = val.strip()
            if val:
                try:
                    obj = self.model.objects.get(**{self.field: val})
                except self.model.DoesNotExist:
                    obj = self.model.objects.create(name=val)
                cleaned_values.append(obj)

        return cleaned_values
