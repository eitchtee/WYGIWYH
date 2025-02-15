from django.forms import widgets, SelectMultiple
from django.urls import reverse
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
        group_by=None,
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
        self.group_by = group_by

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

    def optgroups(self, name, value, attrs=None):
        if not self.group_by:
            # If no group_by is set, return all options as a single list without optgroups
            return [
                (
                    None,
                    [
                        self.create_option(
                            name,
                            option_value,
                            option_label,
                            (str(option_value) in value),
                            index,
                            subindex=None,
                            attrs=attrs,
                        )
                        for index, (option_value, option_label) in enumerate(
                            self.choices
                        )
                    ],
                    0,
                )
            ]

        groups = {}
        has_selected = False
        value = set(value) if value else set()

        for index, (option_value, option_label) in enumerate(self.choices):
            if option_value is None:
                option_value = ""

            # Determine the group key
            if hasattr(option_value, "instance") and hasattr(
                option_value.instance, self.group_by
            ):
                group_key = getattr(option_value.instance, self.group_by) or _(
                    "Ungrouped"
                )
            else:
                group_key = _("Ungrouped")

            group_name = str(group_key) if group_key is not None else None

            if isinstance(option_label, (list, tuple)):
                choices = option_label
            else:
                choices = [(option_value, option_label)]

            if group_name not in groups:
                groups[group_name] = []

            for subvalue, sublabel in choices:
                selected = (not has_selected or self.allow_multiple_selected) and str(
                    subvalue
                ) in value
                has_selected |= selected
                groups[group_name].append(
                    self.create_option(
                        name,
                        subvalue,
                        sublabel,
                        selected,
                        index,
                        subindex=None,
                        attrs=attrs,
                    )
                )

        optgroups = []
        for group_name, subgroup in groups.items():
            optgroups.append((group_name, subgroup, 0))

        return optgroups


class TomSelectMultiple(SelectMultiple, TomSelect):
    pass


class TransactionSelect(TomSelect):
    def __init__(self, income: bool = True, expense: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.load_income = income
        self.load_expense = expense
        self.create = False

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)

        if self.load_income and self.load_expense:
            attrs["data-load"] = reverse("transactions_search")
        elif self.load_income and not self.load_expense:
            attrs["data-load"] = reverse(
                "transactions_search", kwargs={"filter_type": "income"}
            )
        elif self.load_expense and not self.load_income:
            attrs["data-load"] = reverse(
                "transactions_search", kwargs={"filter_type": "expenses"}
            )

        return attrs
