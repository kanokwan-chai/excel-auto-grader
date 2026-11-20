"""Pydantic models for Excel Grading Engine inputs and outputs."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


RuleCategory = Literal[
    "formula",
    "value",
    "position",
    "style",
    "structure",
    "chart",
    "completeness",
]

ImportanceLevel = Literal["low", "normal", "high", "critical"]


class RubricItemConfig(BaseModel):
    id: str
    title: str
    category: RuleCategory
    sheet_name: str | None = None
    target_cell: str | None = None  # e.g., "D2" or "D2:D10"
    rule_config: dict[str, Any] = Field(default_factory=dict)
    max_points: float = Field(ge=0)
    min_points: float = Field(default=0.0, ge=0)
    allow_partial_credit: bool = True
    weight_importance: ImportanceLevel = "normal"
    zero_on_error: bool = False
    is_enabled: bool = True


class RubricConfig(BaseModel):
    id: str = "default"
    name: str = "Default Rubric"
    version: int = 1
    total_points: float = Field(gt=0)
    enabled_categories: list[RuleCategory] = Field(
        default_factory=lambda: [
            "formula",
            "value",
            "position",
            "style",
            "structure",
            "chart",
            "completeness",
        ]
    )
    items: list[RubricItemConfig] = Field(default_factory=list)


class GradingErrorRecord(BaseModel):
    error_code: str
    severity: Literal["info", "warning", "error", "critical"] = "error"
    sheet_name: str | None = None
    cell_reference: str | None = None
    message_th: str
    expected_detail: str | None = None
    actual_detail: str | None = None
    fix_suggestion_th: str | None = None


class RubricItemResult(BaseModel):
    rubric_item_id: str
    item_title: str
    category: RuleCategory
    target_cell: str | None = None
    earned_points: float = 0.0
    deducted_points: float = 0.0
    max_points: float = 0.0
    passed: bool = False
    expected_value: str | None = None
    actual_value: str | None = None
    expected_formula: str | None = None
    actual_formula: str | None = None
    reason: str = ""
    suggestion: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    errors: list[GradingErrorRecord] = Field(default_factory=list)


class FileSecurityReport(BaseModel):
    is_safe: bool
    file_extension: str
    file_size_bytes: int
    sha256_hash: str
    has_macros: bool = False
    uncompressed_size_bytes: int = 0
    warnings: list[str] = Field(default_factory=list)


class WorkbookGradingOutput(BaseModel):
    auto_score: float
    max_score: float
    percentage: float
    recalculated_with_libreoffice: bool = False
    security_report: FileSecurityReport
    details: list[RubricItemResult] = Field(default_factory=list)
    errors: list[GradingErrorRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
