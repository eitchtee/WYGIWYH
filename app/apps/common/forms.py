from crispy_forms.bootstrap import FormActions
from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div, HTML

from apps.common.widgets.tom_select import TomSelect, TomSelectMultiple
from apps.common.models import SharedObject
from apps.common.widgets.crispy.submit import NoClassSubmit

User = get_user_model()


class SharedObjectForm(forms.Form):
    """
    Generic form for editing visibility and sharing settings
    for models inheriting from SharedObject.
    """

    owner = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        label=_("Owner"),
        widget=TomSelect(clear_button=False),
        help_text=_(
            "The owner of this object, if empty all users can see, edit and take ownership."
        ),
    )
    shared_with_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=TomSelectMultiple(clear_button=True),
        label=_("Shared with users"),
        help_text=_("Select users to share this object with"),
    )
    visibility = forms.ChoiceField(
        choices=SharedObject.Visibility.choices,
        required=True,
        label=_("Visibility"),
        help_text=_(
            "Private: Only shown for the owner and shared users. Only editable by the owner."
            "<br/>"
            "Public: Shown for all users. Only editable by the owner."
        ),
    )

    class Meta:
        fields = ["visibility", "shared_with_users"]
        widgets = {
            "visibility": TomSelect(clear_button=False),
        }

    def __init__(self, *args, **kwargs):
        # Get the current user to filter available sharing options
        self.user = kwargs.pop("user", None)
        self.instance = kwargs.pop("instance", None)

        super().__init__(*args, **kwargs)

        # Pre-populate shared users if instance exists
        if self.instance:
            self.fields["shared_with_users"].initial = self.instance.shared_with.all()
            self.fields["visibility"].initial = self.instance.visibility
            self.fields["owner"].initial = self.instance.owner

        # Set up crispy form helper
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field("owner"),
            Field("visibility"),
            HTML("<hr>"),
            Field("shared_with_users"),
            FormActions(
                NoClassSubmit(
                    "submit", _("Save"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        owner = cleaned_data.get("owner")
        shared_with_users = cleaned_data.get("shared_with_users", [])

        # Raise validation error if owner is in shared_with_users
        if owner and owner in shared_with_users:
            self.add_error(
                "shared_with_users",
                ValidationError(
                    _("You cannot share this item with its owner."),
                    code="invalid_share",
                ),
            )

        return cleaned_data

    def save(self):
        instance = self.instance

        instance.visibility = self.cleaned_data["visibility"]
        instance.owner = self.cleaned_data["owner"]

        instance.save()

        # Clear and set shared_with users
        instance.shared_with.set(self.cleaned_data.get("shared_with_users", []))

        return instance
