from crispy_forms.bootstrap import (
    FormActions,
    PrependedText,
    Alert,
)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Div, HTML
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    # AuthenticationForm,
    UsernameField,
    PasswordResetForm,
    SetPasswordForm,
    PasswordChangeForm,
    UserCreationForm,
    AuthenticationForm,
)
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


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
