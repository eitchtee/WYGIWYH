from crispy_bootstrap5.bootstrap5 import Switch, BS5Accordion
from crispy_forms.bootstrap import FormActions, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect
from apps.rules.models import TransactionRule, UpdateOrCreateTransactionRuleAction
from apps.rules.models import TransactionRuleAction


class TransactionRuleForm(forms.ModelForm):
    class Meta:
        model = TransactionRule
        fields = "__all__"
        labels = {
            "on_create": _("Run on creation"),
            "on_update": _("Run on update"),
            "trigger": _("If..."),
        }
        widgets = {"description": forms.widgets.TextInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        # TO-DO: Add helper with available commands
        self.helper.layout = Layout(
            Switch("active"),
            "name",
            Row(Column(Switch("on_update")), Column(Switch("on_create"))),
            "description",
            "trigger",
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )


class TransactionRuleActionForm(forms.ModelForm):
    class Meta:
        model = TransactionRuleAction
        fields = ("value", "field")
        labels = {
            "field": _("Set field"),
            "value": _("To"),
        }
        widgets = {"field": TomSelect(clear_button=False)}

    def __init__(self, *args, **kwargs):
        self.rule = kwargs.pop("rule", None)

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        # TO-DO: Add helper with available commands
        self.helper.layout = Layout(
            "field",
            "value",
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        field = cleaned_data.get("field")

        if field and self.rule:
            # Create a queryset that excludes the current instance
            existing_action = TransactionRuleAction.objects.filter(
                rule=self.rule, field=field
            )

            if self.instance.pk:
                existing_action = existing_action.exclude(pk=self.instance.pk)

            if existing_action.exists():
                raise ValidationError(
                    _("A value for this field already exists in the rule.")
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.rule = self.rule
        if commit:
            instance.save()
        return instance


class UpdateOrCreateTransactionRuleActionForm(forms.ModelForm):
    class Meta:
        model = UpdateOrCreateTransactionRuleAction
        exclude = ("rule",)
        widgets = {
            "search_account_operator": TomSelect(clear_button=False),
            "search_type_operator": TomSelect(clear_button=False),
            "search_is_paid_operator": TomSelect(clear_button=False),
            "search_date_operator": TomSelect(clear_button=False),
            "search_reference_date_operator": TomSelect(clear_button=False),
            "search_amount_operator": TomSelect(clear_button=False),
            "search_description_operator": TomSelect(clear_button=False),
            "search_notes_operator": TomSelect(clear_button=False),
            "search_category_operator": TomSelect(clear_button=False),
            "search_internal_note_operator": TomSelect(clear_button=False),
            "search_internal_id_operator": TomSelect(clear_button=False),
        }

        labels = {
            "search_account_operator": _("Operator"),
            "search_type_operator": _("Operator"),
            "search_is_paid_operator": _("Operator"),
            "search_date_operator": _("Operator"),
            "search_reference_date_operator": _("Operator"),
            "search_amount_operator": _("Operator"),
            "search_description_operator": _("Operator"),
            "search_notes_operator": _("Operator"),
            "search_category_operator": _("Operator"),
            "search_internal_note_operator": _("Operator"),
            "search_internal_id_operator": _("Operator"),
            "search_tags_operator": _("Operator"),
            "search_entities_operator": _("Operator"),
            "search_account": _("Account"),
            "search_type": _("Type"),
            "search_is_paid": _("Paid"),
            "search_date": _("Date"),
            "search_reference_date": _("Reference Date"),
            "search_amount": _("Amount"),
            "search_description": _("Description"),
            "search_notes": _("Notes"),
            "search_category": _("Category"),
            "search_internal_note": _("Internal Note"),
            "search_internal_id": _("Internal ID"),
            "search_tags": _("Tags"),
            "search_entities": _("Entities"),
            "set_account": _("Account"),
            "set_type": _("Type"),
            "set_is_paid": _("Paid"),
            "set_date": _("Date"),
            "set_reference_date": _("Reference Date"),
            "set_amount": _("Amount"),
            "set_description": _("Description"),
            "set_tags": _("Tags"),
            "set_entities": _("Entities"),
            "set_notes": _("Notes"),
            "set_category": _("Category"),
            "set_internal_note": _("Internal Note"),
            "set_internal_id": _("Internal ID"),
        }

    def __init__(self, *args, **kwargs):
        self.rule = kwargs.pop("rule", None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            BS5Accordion(
                AccordionGroup(
                    _("Search Criteria"),
                    Field("filter", rows=1),
                    Row(
                        Column(
                            Field("search_type_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_type", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_is_paid_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_is_paid", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_account_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_account", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_entities_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_entities", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_date_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_date", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_reference_date_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_reference_date", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_description_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_description", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_amount_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_amount", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_category_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_category", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_tags_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_tags", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_notes_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_notes", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_internal_note_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_internal_note", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    Row(
                        Column(
                            Field("search_internal_id_operator"),
                            css_class="form-group col-md-4",
                        ),
                        Column(
                            Field("search_internal_id", rows=1),
                            css_class="form-group col-md-8",
                        ),
                    ),
                    active=True,
                ),
                AccordionGroup(
                    _("Set Values"),
                    Field("set_type", rows=1),
                    Field("set_is_paid", rows=1),
                    Field("set_account", rows=1),
                    Field("set_entities", rows=1),
                    Field("set_date", rows=1),
                    Field("set_reference_date", rows=1),
                    Field("set_description", rows=1),
                    Field("set_amount", rows=1),
                    Field("set_category", rows=1),
                    Field("set_tags", rows=1),
                    Field("set_notes", rows=1),
                    Field("set_internal_note", rows=1),
                    Field("set_internal_id", rows=1),
                    css_class="mb-3",
                    active=True,
                ),
                always_open=True,
            ),
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.rule = self.rule
        if commit:
            instance.save()
        return instance
