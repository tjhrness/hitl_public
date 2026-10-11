"""Safe public validation findings shared by ingestion and configuration."""

from dataclasses import dataclass

from inter_rater_analyzer.domain import ValidationSeverity


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    message: str
    corrective_action: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    worksheet: str | None = None
    item_id: str | None = None
    row: int | None = None
