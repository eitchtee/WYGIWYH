from import_export.widgets import ManyToManyWidget

from apps.export_app.widgets.foreign_key import get_or_create_for_owner, row_owner_id


class AutoCreateManyToManyWidget(ManyToManyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return []

        owner_id = row_owner_id(row)
        return [
            get_or_create_for_owner(self.model, val.strip(), owner_id)
            for val in value.split(self.separator)
            if val.strip()
        ]
