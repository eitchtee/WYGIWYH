from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.transactions.models import (
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
)


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
                    _("Category with this ID does not exist.")
                )
        elif isinstance(data, str):
            category, created = TransactionCategory.objects.get_or_create(name=data)
            return category
        raise serializers.ValidationError(
            _("Invalid category data. Provide an ID or name.")
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
                        _("Tag with this ID does not exist.")
                    )
            elif isinstance(item, str):
                tag, created = TransactionTag.objects.get_or_create(name=item)
            else:
                raise serializers.ValidationError(
                    _("Invalid tag data. Provide an ID or name.")
                )
            tags.append(tag)
        return tags


class TransactionEntityField(serializers.Field):
    def to_representation(self, value):
        return [{"id": entity.id, "name": entity.name} for entity in value.all()]

    def to_internal_value(self, data):
        entities = []
        for item in data:
            if isinstance(item, int):
                try:
                    entity = TransactionEntity.objects.get(pk=item)
                except TransactionTag.DoesNotExist:
                    raise serializers.ValidationError(
                        _("Entity with this ID does not exist.")
                    )
            elif isinstance(item, str):
                entity, created = TransactionEntity.objects.get_or_create(name=item)
            else:
                raise serializers.ValidationError(
                    _("Invalid entity data. Provide an ID or name.")
                )
            entities.append(entity)
        return entities
