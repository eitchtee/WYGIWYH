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
        label=_("E-mail"),
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "E-mail", "name": "email"}
        ),
    )
    password = forms.CharField(
        label=_("Password"),
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
    DATE_FORMAT_CHOICES = [
        ("SHORT_DATE_FORMAT", _("Default")),
        ("d-m-Y", "20-01-2025"),
        ("m-d-Y", "01-20-2025"),
        ("Y-m-d", "2025-01-20"),
        ("d/m/Y", "20/01/2025"),
        ("m/d/Y", "01/20/2025"),
        ("Y/m/d", "2025/01/20"),
        ("d.m.Y", "20.01.2025"),
        ("m.d.Y", "01.20.2025"),
        ("Y.m.d", "2025.01.20"),
    ]

    DATETIME_FORMAT_CHOICES = [
        ("SHORT_DATETIME_FORMAT", _("Default")),
        ("d-m-Y H:i", "20-01-2025 15:30"),
        ("m-d-Y H:i", "01-20-2025 15:30"),
        ("Y-m-d H:i", "2025-01-20 15:30"),
        ("d-m-Y h:i A", "20-01-2025 03:30 PM"),
        ("m-d-Y h:i A", "01-20-2025 03:30 PM"),
        ("Y-m-d h:i A", "2025-01-20 03:30 PM"),
        ("d/m/Y H:i", "20/01/2025 15:30"),
        ("m/d/Y H:i", "01/20/2025 15:30"),
        ("Y/m/d H:i", "2025/01/20 15:30"),
        ("d/m/Y h:i A", "20/01/2025 03:30 PM"),
        ("m/d/Y h:i A", "01/20/2025 03:30 PM"),
        ("Y/m/d h:i A", "2025/01/20 03:30 PM"),
        ("d.m.Y H:i", "20.01.2025 15:30"),
        ("m.d.Y H:i", "01.20.2025 15:30"),
        ("Y.m.d H:i", "2025.01.20 15:30"),
        ("d.m.Y h:i A", "20.01.2025 03:30 PM"),
        ("m.d.Y h:i A", "01.20.2025 03:30 PM"),
        ("Y.m.d h:i A", "2025.01.20 03:30 PM"),
    ]

    NUMBER_FORMAT_CHOICES = [
        ("AA", _("Default")),
        ("DC", "1.234,50"),
        ("CD", "1,234.50"),
    ]

    date_format = forms.ChoiceField(
        choices=DATE_FORMAT_CHOICES, initial="SHORT_DATE_FORMAT", label=_("Date Format")
    )
    datetime_format = forms.ChoiceField(
        choices=DATETIME_FORMAT_CHOICES,
        initial="SHORT_DATETIME_FORMAT",
        label=_("Datetime Format"),
    )

    number_format = forms.ChoiceField(
        choices=NUMBER_FORMAT_CHOICES,
        initial="AA",
        label=_("Number Format"),
    )

    class Meta:
        model = UserSettings
        fields = [
            "language",
            "timezone",
            "start_page",
            "date_format",
            "datetime_format",
            "number_format",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "language",
            "timezone",
            "date_format",
            "datetime_format",
            "number_format",
            "start_page",
            FormActions(
                NoClassSubmit(
                    "submit", _("Save"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )
