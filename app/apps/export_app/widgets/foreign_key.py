from import_export.widgets import ForeignKeyWidget


class AutoCreateForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if value:
            try:
                return super().clean(value, row, **kwargs)
            except self.model.DoesNotExist:
                return self.model.objects.create(name=value)
        return None


class SkipMissingForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None

        try:
            return super().clean(value, row, *args, **kwargs)
        except self.model.DoesNotExist:
            return None
