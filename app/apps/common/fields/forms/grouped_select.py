from django import forms
from django.forms.models import ModelChoiceIterator
from django.utils.translation import gettext_lazy as _


class GroupedModelChoiceIterator(ModelChoiceIterator):
    def __init__(self, field, group_by):
        self.group_by = group_by
        super().__init__(field)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield "", self.field.empty_label

        queryset = self.queryset
        grouped_queryset = {}

        for obj in queryset:
            group_key = getattr(obj, self.group_by, None) if self.group_by else None
            grouped_queryset.setdefault(group_key, []).append(obj)

        for group, items in grouped_queryset.items():
            yield (
                group if group is not None else _("Ungrouped"),
                [
                    (self.field.prepare_value(obj), self.field.label_from_instance(obj))
                    for obj in items
                ],
            )


class GroupedModelChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, group_by=None, **kwargs):
        self.group_by = group_by
        super().__init__(*args, **kwargs)

    @property
    def choices(self):
        return GroupedModelChoiceIterator(self, self.group_by)


class GroupedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, group_by=None, **kwargs):
        self.group_by = group_by
        super().__init__(*args, **kwargs)

    @property
    def choices(self):
        return GroupedModelChoiceIterator(self, self.group_by)
