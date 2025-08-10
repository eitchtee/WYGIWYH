from crispy_forms.bootstrap import (
    FormActions,
)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field, Div, HTML
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    UsernameField,
    AuthenticationForm,
    UserCreationForm,
)
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.users.models import UserSettings
from apps.common.middleware.thread_local import get_current_user


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
            Submit("Submit", "Login", css_class="btn btn-primary w-100"),
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
        ("SD", "1 234.50"),
        ("SC", "1 234,50"),
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
            "volume",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "language",
            "timezone",
            HTML("<hr />"),
            "date_format",
            "datetime_format",
            "number_format",
            HTML("<hr />"),
            "start_page",
            HTML("<hr />"),
            "volume",
            FormActions(
                NoClassSubmit(
                    "submit", _("Save"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )

        self.fields["language"].help_text = _(
            "This changes the language (if available) and how numbers and dates are displayed\n"
            "Consider helping translate WYGIWYH to your language at %(translation_link)s"
        ) % {
            "translation_link": '<a href="https://translations.herculino.com" target="_blank">translations.herculino.com</a>'
        }


class UserUpdateForm(forms.ModelForm):
    new_password1 = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
        help_text=_("Leave blank to keep the current password."),
    )
    new_password2 = forms.CharField(
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
    )

    class Meta:
        model = get_user_model()
        # Add the administrative fields
        fields = ["first_name", "last_name", "email", "is_active", "is_superuser"]
        # Help texts can be defined here or directly in the layout/field definition
        help_texts = {
            "is_active": _(
                "Designates whether this user should be treated as active. Unselect this instead of deleting accounts."
            ),
            "is_superuser": _(
                "Designates that this user has all permissions without explicitly assigning them."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = kwargs.get("instance")  # Store instance for validation/checks
        self.requesting_user = get_current_user()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        # Define the layout using Crispy Forms, including the new fields
        self.helper.layout = Layout(
            Row(
                Column("first_name", css_class="form-group col-md-6"),
                Column("last_name", css_class="form-group col-md-6"),
                css_class="row",
            ),
            Field("email"),
            # Group password fields (optional visual grouping)
            Div(
                Field("new_password1"),
                Field("new_password2"),
                css_class="border p-3 rounded mb-3",
            ),
            # Group administrative status fields
            Div(
                Field("is_active"),
                Field("is_superuser"),
                css_class="border p-3 rounded mb-3 text-bg-secondary",  # Example visual separation
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

        if (
            self.requesting_user == self.instance
            or not self.requesting_user.is_superuser
        ):
            self.fields["is_superuser"].disabled = True
            self.fields["is_active"].disabled = True

    # Keep existing clean methods
    def clean_email(self):
        email = self.cleaned_data.get("email")
        # Use case-insensitive comparison for email uniqueness check
        if (
            self.instance
            and get_user_model()
            .objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                _("This email address is already in use by another account.")
            )
        return email

    def clean_new_password2(self):
        new_password1 = self.cleaned_data.get("new_password1")
        new_password2 = self.cleaned_data.get("new_password2")
        if new_password1 and new_password1 != new_password2:
            raise forms.ValidationError(_("The two password fields didn't match."))
        if new_password1 and not new_password2:
            raise forms.ValidationError(_("Please confirm your new password."))
        if new_password2 and not new_password1:
            raise forms.ValidationError(_("Please enter the new password first."))
        return new_password2

    def clean(self):
        cleaned_data = super().clean()
        is_active_val = cleaned_data.get("is_active")
        is_superuser_val = cleaned_data.get("is_superuser")

        # --- Crucial Security Check Example ---
        # Prevent the requesting user from deactivating or removing superuser status
        # from their *own* account via this form.
        if (
            self.requesting_user
            and self.instance
            and self.requesting_user.pk == self.instance.pk
        ):
            # Check if 'is_active' field exists and user is trying to set it to False
            if "is_active" in self.fields and is_active_val is False:
                self.add_error(
                    "is_active",
                    _("You cannot deactivate your own account using this form."),
                )

            # Check if 'is_superuser' field exists, the user *is* currently a superuser,
            # and they are trying to set it to False
            if (
                "is_superuser" in self.fields
                and self.instance.is_superuser
                and is_superuser_val is False
            ):
                if get_user_model().objects.filter(is_superuser=True).count() <= 1:
                    self.add_error(
                        "is_superuser",
                        _("Cannot remove status from the last superuser."),
                    )
                else:
                    self.add_error(
                        "is_superuser",
                        _(
                            "You cannot remove your own superuser status using this form."
                        ),
                    )

        return cleaned_data

    # Save method remains the same, ModelForm handles boolean fields correctly
    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get("new_password1")
        if new_password:
            user.set_password(new_password)

        if commit:
            user.save()
        return user


class UserAddForm(UserCreationForm):
    """
    A form for administrators to create new users.
    Includes fields for first name, last name, email, active status,
    and superuser status. Uses email as the username field.
    Inherits password handling from UserCreationForm.
    """

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        # Specify the fields to include. UserCreationForm automatically handles
        # 'password1' and 'password2'. We replace 'username' with 'email'.
        fields = ("email", "first_name", "last_name", "is_active", "is_superuser")
        field_classes = {
            "email": forms.EmailField
        }  # Ensure email field uses EmailField validation
        help_texts = {
            "is_active": _(
                "Designates whether this user should be treated as active. Unselect this instead of deleting accounts."
            ),
            "is_superuser": _(
                "Designates that this user has all permissions without explicitly assigning them."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set is_active to True by default for new users, can be overridden by admin
        self.fields["is_active"].initial = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        # Define the layout, including password fields from UserCreationForm
        self.helper.layout = Layout(
            Field("email"),
            Row(
                Column("first_name", css_class="form-group col-md-6"),
                Column("last_name", css_class="form-group col-md-6"),
                css_class="row",
            ),
            # UserCreationForm provides 'password1' and 'password2' fields
            Div(
                Field("password1", autocomplete="new-password"),
                Field("password2", autocomplete="new-password"),
                css_class="border p-3 rounded mb-3",
            ),
            # Administrative status fields
            Div(
                Field("is_active"),
                Field("is_superuser"),
                css_class="border p-3 rounded mb-3 text-bg-secondary",
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

    def clean_email(self):
        """Ensure email uniqueness (case-insensitive)."""
        email = self.cleaned_data.get("email")
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("A user with this email address already exists.")
            )
        return email

    @transaction.atomic  # Ensure user creation is atomic
    def save(self, commit=True):
        """
        Save the user instance. UserCreationForm's save handles password hashing.
        Our Meta class ensures other fields are included.
        """
        user = super().save(commit=False)

        if commit:
            user.save()
        return user
