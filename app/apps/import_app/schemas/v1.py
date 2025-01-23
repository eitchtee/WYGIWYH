from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator, field_validator


class CompareDeduplicationRule(BaseModel):
    type: Literal["compare"]
    fields: Dict = Field(
        ..., description="Match header and fields to compare for deduplication"
    )
    match_type: Literal["lax", "strict"]

    @field_validator("fields", mode="before")
    def coerce_fields_to_dict(cls, v):
        if isinstance(v, list):
            return {k: v for d in v for k, v in d.items()}
        return v


class ReplaceTransformationRule(BaseModel):
    type: Literal["replace", "regex"] = Field(
        ..., description="Type of transformation: replace or regex"
    )
    pattern: str = Field(..., description="Pattern to match")
    replacement: str = Field(..., description="Value to replace with")
    exclusive: bool = Field(
        default=False,
        description="If it should match against the last transformation or the original value",
    )


class DateFormatTransformationRule(BaseModel):
    type: Literal["date_format"] = Field(
        ..., description="Type of transformation: date_format"
    )
    original_format: str = Field(..., description="Original date format")
    new_format: str = Field(..., description="New date format to use")


class HashTransformationRule(BaseModel):
    fields: List[str]
    type: Literal["hash"]


class MergeTransformationRule(BaseModel):
    fields: List[str]
    type: Literal["merge"]
    separator: str = Field(default=" ", description="Separator to use when merging")


class SplitTransformationRule(BaseModel):
    type: Literal["split"]
    separator: str = Field(default=",", description="Separator to use when splitting")
    index: int | None = Field(
        default=0, description="Index to return as value. Empty to return all."
    )


class CSVImportSettings(BaseModel):
    skip_errors: bool = Field(
        default=False,
        description="If True, errors during import will be logged and skipped",
    )
    file_type: Literal["csv"] = "csv"
    delimiter: str = Field(default=",", description="CSV delimiter character")
    encoding: str = Field(default="utf-8", description="File encoding")
    skip_lines: int = Field(
        default=0, description="Number of rows to skip at the beginning of the file"
    )
    trigger_transaction_rules: bool = True
    importing: Literal[
        "transactions", "accounts", "currencies", "categories", "tags", "entities"
    ]


class ColumnMapping(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="CSV column header. If None, the field will be generated from transformations",
    )
    default: Optional[str] = None
    required: bool = False
    transformations: Optional[
        List[
            ReplaceTransformationRule
            | DateFormatTransformationRule
            | HashTransformationRule
            | MergeTransformationRule
            | SplitTransformationRule
        ]
    ] = Field(default_factory=list)


class TransactionAccountMapping(ColumnMapping):
    target: Literal["account"] = Field(..., description="Transaction field to map to")
    type: Literal["id", "name"] = "name"
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)
    required: bool = Field(True, frozen=True)


class TransactionTypeMapping(ColumnMapping):
    target: Literal["type"] = Field(..., description="Transaction field to map to")
    detection_method: Literal["sign", "always_income", "always_expense"] = "sign"
    coerce_to: Literal["transaction_type"] = Field("transaction_type", frozen=True)


class TransactionIsPaidMapping(ColumnMapping):
    target: Literal["is_paid"] = Field(..., description="Transaction field to map to")
    detection_method: Literal["sign", "boolean", "always_paid", "always_unpaid"]
    coerce_to: Literal["is_paid"] = Field("is_paid", frozen=True)


class TransactionDateMapping(ColumnMapping):
    target: Literal["date"] = Field(..., description="Transaction field to map to")
    format: List[str] | str
    coerce_to: Literal["date"] = Field("date", frozen=True)
    required: bool = Field(True, frozen=True)


class TransactionReferenceDateMapping(ColumnMapping):
    target: Literal["reference_date"] = Field(
        ..., description="Transaction field to map to"
    )
    format: List[str] | str
    coerce_to: Literal["date"] = Field("date", frozen=True)


class TransactionAmountMapping(ColumnMapping):
    target: Literal["amount"] = Field(..., description="Transaction field to map to")
    coerce_to: Literal["positive_decimal"] = Field("positive_decimal", frozen=True)
    required: bool = Field(True, frozen=True)


class TransactionDescriptionMapping(ColumnMapping):
    target: Literal["description"] = Field(
        ..., description="Transaction field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class TransactionNotesMapping(ColumnMapping):
    target: Literal["notes"] = Field(..., description="Transaction field to map to")
    coerce_to: Literal["str"] = Field("str", frozen=True)


class TransactionTagsMapping(ColumnMapping):
    target: Literal["tags"] = Field(..., description="Transaction field to map to")
    type: Literal["id", "name"] = "name"
    create: bool = Field(
        default=True, description="Create new tags if they doesn't exist"
    )
    coerce_to: Literal["list"] = Field("list", frozen=True)


class TransactionEntitiesMapping(ColumnMapping):
    target: Literal["entities"] = Field(..., description="Transaction field to map to")
    create: bool = Field(
        default=True, description="Create new entities if they doesn't exist"
    )
    coerce_to: Literal["list"] = Field("list", frozen=True)


class TransactionCategoryMapping(ColumnMapping):
    target: Literal["category"] = Field(..., description="Transaction field to map to")
    create: bool = Field(
        default=True, description="Create category if it doesn't exist"
    )
    type: Literal["id", "name"] = "name"
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)


class TransactionInternalNoteMapping(ColumnMapping):
    target: Literal["internal_note"] = Field(
        ..., description="Transaction field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class TransactionInternalIDMapping(ColumnMapping):
    target: Literal["internal_id"] = Field(
        ..., description="Transaction field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CategoryNameMapping(ColumnMapping):
    target: Literal["category_name"] = Field(
        ..., description="Category field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CategoryMuteMapping(ColumnMapping):
    target: Literal["category_mute"] = Field(
        ..., description="Category field to map to"
    )
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class CategoryActiveMapping(ColumnMapping):
    target: Literal["category_active"] = Field(
        ..., description="Category field to map to"
    )
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class TagNameMapping(ColumnMapping):
    target: Literal["tag_name"] = Field(..., description="Tag field to map to")
    coerce_to: Literal["str"] = Field("str", frozen=True)


class TagActiveMapping(ColumnMapping):
    target: Literal["tag_active"] = Field(..., description="Tag field to map to")
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class EntityNameMapping(ColumnMapping):
    target: Literal["entity_name"] = Field(..., description="Entity field to map to")
    coerce_to: Literal["str"] = Field("str", frozen=True)


class EntityActiveMapping(ColumnMapping):
    target: Literal["entity_active"] = Field(..., description="Entity field to map to")
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class AccountNameMapping(ColumnMapping):
    target: Literal["account_name"] = Field(..., description="Account field to map to")
    coerce_to: Literal["str"] = Field("str", frozen=True)


class AccountGroupMapping(ColumnMapping):
    target: Literal["account_group"] = Field(..., description="Account field to map to")
    type: Literal["id", "name"]
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)


class AccountCurrencyMapping(ColumnMapping):
    target: Literal["account_currency"] = Field(
        ..., description="Account field to map to"
    )
    type: Literal["id", "name", "code"]
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)


class AccountExchangeCurrencyMapping(ColumnMapping):
    target: Literal["account_exchange_currency"] = Field(
        ..., description="Account field to map to"
    )
    type: Literal["id", "name", "code"]
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)


class AccountIsAssetMapping(ColumnMapping):
    target: Literal["account_is_asset"] = Field(
        ..., description="Account field to map to"
    )
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class AccountIsArchivedMapping(ColumnMapping):
    target: Literal["account_is_archived"] = Field(
        ..., description="Account field to map to"
    )
    coerce_to: Literal["bool"] = Field("bool", frozen=True)


class CurrencyCodeMapping(ColumnMapping):
    target: Literal["currency_code"] = Field(
        ..., description="Currency field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CurrencyNameMapping(ColumnMapping):
    target: Literal["currency_name"] = Field(
        ..., description="Currency field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CurrencyDecimalPlacesMapping(ColumnMapping):
    target: Literal["currency_decimal_places"] = Field(
        ..., description="Currency field to map to"
    )
    coerce_to: Literal["int"] = Field("int", frozen=True)


class CurrencyPrefixMapping(ColumnMapping):
    target: Literal["currency_prefix"] = Field(
        ..., description="Currency field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CurrencySuffixMapping(ColumnMapping):
    target: Literal["currency_suffix"] = Field(
        ..., description="Currency field to map to"
    )
    coerce_to: Literal["str"] = Field("str", frozen=True)


class CurrencyExchangeMapping(ColumnMapping):
    target: Literal["currency_exchange"] = Field(
        ..., description="Currency field to map to"
    )
    type: Literal["id", "name", "code"]
    coerce_to: Literal["str|int"] = Field("str|int", frozen=True)


class ImportProfileSchema(BaseModel):
    settings: CSVImportSettings
    mapping: Dict[
        str,
        TransactionAccountMapping
        | TransactionTypeMapping
        | TransactionIsPaidMapping
        | TransactionDateMapping
        | TransactionReferenceDateMapping
        | TransactionAmountMapping
        | TransactionDescriptionMapping
        | TransactionNotesMapping
        | TransactionTagsMapping
        | TransactionEntitiesMapping
        | TransactionCategoryMapping
        | TransactionInternalNoteMapping
        | TransactionInternalIDMapping
        | CategoryNameMapping
        | CategoryMuteMapping
        | CategoryActiveMapping
        | TagNameMapping
        | TagActiveMapping
        | EntityNameMapping
        | EntityActiveMapping
        | AccountNameMapping
        | AccountGroupMapping
        | AccountCurrencyMapping
        | AccountExchangeCurrencyMapping
        | AccountIsAssetMapping
        | AccountIsArchivedMapping
        | CurrencyCodeMapping
        | CurrencyNameMapping
        | CurrencyDecimalPlacesMapping
        | CurrencyPrefixMapping
        | CurrencySuffixMapping
        | CurrencyExchangeMapping,
    ]
    deduplication: List[CompareDeduplicationRule] = Field(
        default_factory=list,
        description="Rules for deduplicating records during import",
    )

    @model_validator(mode="after")
    def validate_mappings(self) -> "ImportProfileSchema":
        import_type = self.settings.importing

        # Define allowed mapping types for each import type
        allowed_mappings = {
            "transactions": (
                TransactionAccountMapping,
                TransactionTypeMapping,
                TransactionIsPaidMapping,
                TransactionDateMapping,
                TransactionReferenceDateMapping,
                TransactionAmountMapping,
                TransactionDescriptionMapping,
                TransactionNotesMapping,
                TransactionTagsMapping,
                TransactionEntitiesMapping,
                TransactionCategoryMapping,
                TransactionInternalNoteMapping,
                TransactionInternalIDMapping,
            ),
            "accounts": (
                AccountNameMapping,
                AccountGroupMapping,
                AccountCurrencyMapping,
                AccountExchangeCurrencyMapping,
                AccountIsAssetMapping,
                AccountIsArchivedMapping,
            ),
            "currencies": (
                CurrencyCodeMapping,
                CurrencyNameMapping,
                CurrencyDecimalPlacesMapping,
                CurrencyPrefixMapping,
                CurrencySuffixMapping,
                CurrencyExchangeMapping,
            ),
            "categories": (
                CategoryNameMapping,
                CategoryMuteMapping,
                CategoryActiveMapping,
            ),
            "tags": (TagNameMapping, TagActiveMapping),
            "entities": (EntityNameMapping, EntityActiveMapping),
        }

        allowed_types = allowed_mappings[import_type]

        for field_name, mapping in self.mapping.items():
            if not isinstance(mapping, allowed_types):
                raise ValueError(
                    f"Mapping type '{type(mapping).__name__}' is not allowed when importing {import_type}. "
                    f"Allowed types are: {', '.join(t.__name__ for t in allowed_types)}"
                )

        return self
