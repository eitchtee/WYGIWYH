from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class CompareDeduplicationRule(BaseModel):
    type: Literal["compare"]
    fields: Dict = Field(
        ..., description="Match header and fields to compare for deduplication"
    )
    match_type: Literal["lax", "strict"]


class ReplaceTransformationRule(BaseModel):
    field: str
    type: Literal["replace", "regex"] = Field(
        ..., description="Type of transformation: replace or regex"
    )
    pattern: str = Field(..., description="Pattern to match")
    replacement: str = Field(..., description="Value to replace with")


class DateFormatTransformationRule(BaseModel):
    field: str
    type: Literal["date_format"] = Field(
        ..., description="Type of transformation: replace or regex"
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
    fields: List[str]
    type: Literal["split"]
    separator: str = Field(default=",", description="Separator to use when splitting")
    index: int | None = Field(
        default=0, description="Index to return as value. Empty to return all."
    )


class ImportSettings(BaseModel):
    skip_errors: bool = Field(
        default=False,
        description="If True, errors during import will be logged and skipped",
    )
    file_type: Literal["csv"] = "csv"
    delimiter: str = Field(default=",", description="CSV delimiter character")
    encoding: str = Field(default="utf-8", description="File encoding")
    skip_rows: int = Field(
        default=0, description="Number of rows to skip at the beginning of the file"
    )
    importing: Literal[
        "transactions", "accounts", "currencies", "categories", "tags", "entities"
    ]


class ColumnMapping(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="CSV column header. If None, the field will be generated from transformations",
    )
    target: Literal[
        "account",
        "type",
        "is_paid",
        "date",
        "reference_date",
        "amount",
        "notes",
        "category",
        "tags",
        "entities",
        "internal_note",
    ] = Field(..., description="Transaction field to map to")
    default_value: Optional[str] = None
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


class ImportProfileSchema(BaseModel):
    settings: ImportSettings
    column_mapping: Dict[str, ColumnMapping]
    deduplication: List[CompareDeduplicationRule] = Field(
        default_factory=list,
        description="Rules for deduplicating records during import",
    )
