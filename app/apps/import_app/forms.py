from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
)
from django import forms
from django.utils.translation import gettext_lazy as _
from django_ace import AceWidget

from apps.import_app.models import ImportProfile
from apps.common.widgets.crispy.submit import NoClassSubmit


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


class ImportRunFileUploadForm(forms.Form):
    file = forms.FileField(label=_("Select a file"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "file",
            FormActions(
                NoClassSubmit(
                    "submit", _("Import"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )
