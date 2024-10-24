from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.rules.models import TransactionRule
from apps.rules.models import TransactionRuleAction
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect


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
            if TransactionRuleAction.objects.filter(
                rule=self.rule, field=field
            ).exists():
                raise ValidationError(
                    _("A value for this field already exists in the rule.")
                )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.rule = self.rule
        if commit:
            instance.save()
        return instance
