from crispy_forms.bootstrap import (
    FormActions,
)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit
from django import forms
from django.contrib.auth.forms import (
    UsernameField,
    AuthenticationForm,
)
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.users.models import UserSettings


class LoginForm(AuthenticationForm):
    username = UsernameField(
        label="Seu e-mail",
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "E-mail", "name": "email"}
        ),
    )
    password = forms.CharField(
        label="Sua senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Senha"}
        ),
    )

    error_messages = {
        "invalid_login": _("Invalid e-mail or password"),
        "inactive": _("This account is deactivated"),
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            "username",
            "password",
            Submit("Submit", "Login"),
        )


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ["language", "timezone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "language",
            "timezone",
            FormActions(
                NoClassSubmit(
                    "submit", _("Save"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )
