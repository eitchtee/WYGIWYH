from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.widgets.tom_select import TomSelect, TomSelectMultiple


# class DynamicModelChoiceField(forms.ModelChoiceField):
#     def __init__(self, model, *args, **kwargs):
#         self.model = model
#         self.queryset = kwargs.pop("queryset", model.objects.all())
#         super().__init__(queryset=self.queryset, *args, **kwargs)
#         self._created_instance = None
#
#         self.widget = TomSelect(clear_button=True, create=True)
#
#     def to_python(self, value):
#         if value in self.empty_values:
#             return None
#         try:
#             key = self.to_field_name or "pk"
#             return self.model.objects.get(**{key: value})
#         except (ValueError, TypeError, self.model.DoesNotExist):
#             return value  # Return the raw value; we'll handle creation in clean()
#
#     def clean(self, value):
#         if isinstance(value, self.model):
#             return value
#         if isinstance(value, str):
#             try:
#                 if value.isdigit():
#                     return self.model.objects.get(id=value)
#                 else:
#                     raise self.model.DoesNotExist
#             except self.model.DoesNotExist:
#                 try:
#                     with transaction.atomic():
#                         instance = self.model.objects.create(name=value)
#                         self._created_instance = instance
#                         return instance
#                 except Exception as e:
#                     raise ValidationError(
#                         self.error_messages["invalid_choice"], code="invalid_choice"
#                     )
#         return super().clean(value)
#
#     def bound_data(self, data, initial):
#         if self._created_instance and isinstance(data, str):
#             if data == self._created_instance.name:
#                 return self._created_instance.pk
#         return super().bound_data(data, initial)


class DynamicModelChoiceField(forms.ModelChoiceField):
    def __init__(self, model, *args, **kwargs):
        self.model = model
        self.queryset = kwargs.pop("queryset", model.objects.all())
        super().__init__(queryset=self.queryset, *args, **kwargs)
        self._created_instance = None

        self.widget = TomSelect(clear_button=True, create=True)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or "pk"
            return self.model.objects.get(**{key: value})
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
                try:
                    with transaction.atomic():
                        instance = self.model.objects.create(name=value)
                        self._created_instance = instance
                        return instance
                except Exception as e:
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
        Initialize the CreateIfNotExistsModelMultipleChoiceField.

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
                new_instance = self.queryset.model(**{self.create_field: value})
                new_instance.full_clean()
                new_instance.save()
            return new_instance
        except Exception as e:
            raise ValidationError(f"Error creating new instance: {str(e)}")

    def clean(self, value):
        """
        Clean and validate the field value.

        This method checks if each selected choice exists in the database.
        If a choice doesn't exist, it creates a new instance of the model.

        Args:
            value (list): List of selected values.

        Returns:
            list: A list containing all selected and newly created model instances.

        Raises:
            ValidationError: If there's an error during the cleaning process.
        """
        if not value:
            return []

        print(value)

        string_values = set(str(v) for v in value)
        existing_objects = list(
            self.queryset.filter(**{f"{self.create_field}__in": string_values})
        )
        existing_values = set(
            str(getattr(obj, self.create_field)) for obj in existing_objects
        )

        new_values = string_values - existing_values
        new_objects = []

        for new_value in new_values:
            try:
                new_objects.append(self._create_new_instance(new_value))
            except ValidationError as e:
                raise ValidationError(f"Error creating '{new_value}': {str(e)}")

        return existing_objects + new_objects
