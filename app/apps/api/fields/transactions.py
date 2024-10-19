from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.transactions.models import TransactionCategory, TransactionTag


@extend_schema_field(
    {
        "oneOf": [{"type": "string"}, {"type": "integer"}],
        "description": "TransactionCategory ID or name. If the name doesn't exist, a new one will be created",
    }
)
class TransactionCategoryField(serializers.Field):
    def to_representation(self, value):
        return {"id": value.id, "name": value.name}

    def to_internal_value(self, data):
        if isinstance(data, int):
            try:
                return TransactionCategory.objects.get(pk=data)
            except TransactionCategory.DoesNotExist:
                raise serializers.ValidationError(
                    "Category with this ID does not exist."
                )
        elif isinstance(data, str):
            category, created = TransactionCategory.objects.get_or_create(name=data)
            return category
        raise serializers.ValidationError(
            "Invalid category data. Provide an ID or name."
        )

    @staticmethod
    def get_schema():
        return {
            "type": "array",
            "items": {"type": "string", "description": "TransactionTag ID or name"},
        }


@extend_schema_field(
    {
        "type": "array",
        "items": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        "description": "TransactionTag ID or name. If the name doesn't exist, a new one will be created",
    }
)
class TransactionTagField(serializers.Field):
    def to_representation(self, value):
        return [{"id": tag.id, "name": tag.name} for tag in value.all()]

    def to_internal_value(self, data):
        tags = []
        for item in data:
            if isinstance(item, int):
                try:
                    tag = TransactionTag.objects.get(pk=item)
                except TransactionTag.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Tag with ID {item} does not exist."
                    )
            elif isinstance(item, str):
                tag, created = TransactionTag.objects.get_or_create(name=item)
            else:
                raise serializers.ValidationError(
                    "Invalid tag data. Provide an ID or name."
                )
            tags.append(tag)
        return tags
