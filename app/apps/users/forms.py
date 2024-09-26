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
)
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV3
from unfold.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = UsernameField(
        label="Seu e-mail",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "E-mail"}
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
        "invalid_login": _("E-mail ou senha inválidos."),
        "inactive": _("Esta conta esta desativada."),
    }
