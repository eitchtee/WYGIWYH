from apps.accounts.models import Account
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect
from apps.import_app.models import ImportProfile
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
)
from django import forms
from django.utils.translation import gettext_lazy as _


class ImportProfileForm(forms.ModelForm):
    class Meta:
        model = ImportProfile
        fields = [
            "name",
            "version",
            "yaml_config",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout("name", "version", "yaml_config")

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )


class ImportRunFileUploadForm(forms.Form):
    file = forms.FileField(label=_("Select a file"))
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        required=False,
        label=_("Account"),
        help_text=_(
            "Import every transaction into this account. Leave empty to let the "
            "profile pick the account."
        ),
        widget=TomSelect(group_by="group"),
    )

    def __init__(self, *args, profile, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout("file")

        if profile.imports_transactions:
            self.fields["account"].queryset = Account.objects.filter(is_archived=False)
            self.helper.layout.append("account")
        else:
            # Only transactions belong to an account
            del self.fields["account"]

        self.helper.layout.append(
            FormActions(
                NoClassSubmit("submit", _("Import"), css_class="btn btn-primary"),
            ),
        )
