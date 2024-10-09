from django.forms import widgets, SelectMultiple
from django.utils.translation import gettext_lazy as _


class TomSelect(widgets.Select):
    def __init__(
        self,
        attrs=None,
        remove_button=False,
        remove_button_text=_("Remove"),
        create=False,
        create_text=_("Add"),
        clear_button=True,
        clear_text=_("Clear"),
        no_results_text=_("No results..."),
        checkboxes=False,
        *args,
        **kwargs
    ):
        super().__init__(attrs, *args, **kwargs)
        self.remove_button = remove_button
        self.remove_button_text = remove_button_text
        self.clear_button = clear_button
        self.create = create
        self.create_text = create_text
        self.clear_text = clear_text
        self.no_results_text = no_results_text
        self.checkboxes = checkboxes

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)

        attrs["data-txt-no-results"] = self.no_results_text

        if self.remove_button:
            attrs["data-remove-button"] = "true"
            attrs["data-txt-remove"] = self.remove_button_text

        if self.create:
            attrs["data-create"] = "true"
            attrs["data-txt-create"] = self.create_text

        if self.clear_button:
            attrs["data-clear-button"] = "true"
            attrs["data-txt-clear"] = self.clear_text

        if self.checkboxes:
            attrs["data-checkboxes"] = "true"

        return attrs


class TomSelectMultiple(SelectMultiple, TomSelect):
    pass
