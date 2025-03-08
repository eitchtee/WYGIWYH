from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.tom_select import TomSelect, TomSelectMultiple
from apps.common.middleware.thread_local import get_current_user


class DynamicModelChoiceField(forms.ModelChoiceField):
    def __init__(self, model, *args, **kwargs):
        self.model = model
        self.to_field_name = kwargs.pop("to_field_name", "pk")

        self.create_field = kwargs.pop("create_field", None)

        self.queryset = kwargs.pop("queryset", model.objects.all())

        self.widget = TomSelect(clear_button=True, create=True)

        super().__init__(queryset=self.queryset, *args, **kwargs)
        self._created_instance = None

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return self.model.objects.get(**{self.to_field_name: value})
        except (ValueError, TypeError, self.model.DoesNotExist):
            return value  # Return the raw value; we'll handle creation in clean()

    def clean(self, value):
        if value in self.empty_values:
            if self.required:
                raise ValidationError(self.error_messages["required"], code="required")
            return None

        if isinstance(value, self.model):
            return value

        if isinstance(value, str):
            value = value.strip()
            if not value:
                if self.required:
                    raise ValidationError(
                        self.error_messages["required"], code="required"
                    )
                return None

            try:
                if value.isdigit():
                    return self.model.objects.get(id=value)
                else:
                    raise self.model.DoesNotExist
            except self.model.DoesNotExist:
                if self.create_field:
                    try:
                        with transaction.atomic():
                            # First try to get the object
                            lookup = {self.create_field: value}
                            try:
                                instance = self.model.objects.get(**lookup)
                            except self.model.DoesNotExist:
                                # Create a new instance directly
                                instance = self.model(**lookup)
                                instance.save()

                            self._created_instance = instance
                            return instance
                    except Exception as e:
                        raise ValidationError(_("Error creating new instance"))
                else:
                    raise ValidationError(
                        self.error_messages["invalid_choice"], code="invalid_choice"
                    )

        return super().clean(value)

    def bound_data(self, data, initial):
        if self._created_instance and isinstance(data, str):
            if data == self._created_instance.name:
                return self._created_instance.pk
        return super().bound_data(data, initial)


class DynamicModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """
    A custom ModelMultipleChoiceField that creates new entries if they don't exist.

    This field allows users to select multiple existing options or add new ones.
    If a selected option doesn't exist, it will be created in the database.

    Attributes:
        create_field (str): The name of the field to use when creating new instances.
    """

    def __init__(self, model, **kwargs):
        """
        Args:
            create_field (str): The name of the field to use when creating new instances.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        self.create_field = kwargs.pop("create_field", None)
        if not self.create_field:
            raise ValueError("The 'create_field' parameter is required.")
        self.model = model
        self.queryset = kwargs.pop("queryset", model.objects.all())
        super().__init__(queryset=self.queryset, **kwargs)

        self.widget = TomSelectMultiple(
            remove_button=True, clear_button=True, create=True, checkboxes=True
        )

    def _create_new_instance(self, value):
        """
        Create a new instance of the model with the given value.

        Args:
            value: The value to use for creating the new instance.

        Returns:
            Model: The newly created model instance.

        Raises:
            ValidationError: If there's an error creating the new instance.
        """
        try:
            with transaction.atomic():
                # Check if exists first without using update_or_create
                lookup = {self.create_field: value}
                try:
                    # Use base manager to bypass distinct filters
                    instance = self.model.objects.get(**lookup)
                    return instance
                except self.model.DoesNotExist:
                    # Create a new instance directly
                    instance = self.model(**lookup)
                    instance.save()
                    return instance
        except Exception as e:
            print(e)
            raise ValidationError(_("Error creating new instance"))

    def clean(self, value):
        if not value:
            return []

        string_values = set(str(v) for v in value)

        # Get existing objects first
        existing_objects = list(
            self.queryset.filter(**{f"{self.create_field}__in": string_values})
        )
        existing_values = set(
            str(getattr(obj, self.create_field)) for obj in existing_objects
        )

        # Create new objects for missing values
        new_values = string_values - existing_values
        new_objects = []

        for new_value in new_values:
            new_objects.append(self._create_new_instance(new_value))

        return existing_objects + new_objects
