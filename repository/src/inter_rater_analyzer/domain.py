"""Canonical immutable domain values. No Qt or persistence dependencies."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4


class RatingType(StrEnum):
    BINARY = "Binary"
    NOMINAL = "Nominal"
    ORDINAL = "Ordinal"
    CONTINUOUS = "Continuous"


class VersionStatus(StrEnum):
    DRAFT = "Draft"
    COMPLETED = "Completed"
    FAILED = "Failed"
    ABANDONED = "Abandoned"


class VersionType(StrEnum):
    DATA_CHANGE = "Data Change"
    CONFIGURATION_ONLY = "Configuration Only"


class ValidationSeverity(StrEnum):
    ERROR = "Error"
    WARNING = "Warning"


class MetricScope(StrEnum):
    OVERALL = "Overall"
    PAIRWISE = "Pairwise"
    BOTH = "Both"


class BackupType(StrEnum):
    MANUAL = "Manual"
    PRE_RESTORE = "Pre-Restore"


class ErrorFamily(StrEnum):
    FILE = "FILE"
    VALIDATION = "VALIDATION"
    STAT = "STAT"
    REPORT = "REPORT"
    BACKUP = "BACKUP"
    RESTORE = "RESTORE"
    DB = "DB"
    SYSTEM = "SYSTEM"


class ErrorCode(StrEnum):
    FILE_INVALID = "FILE_INVALID"
    VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
    VALIDATION_VALUE = "VALIDATION_VALUE"
    STAT_UNDEFINED = "STAT_UNDEFINED"
    REPORT_FAILED = "REPORT_FAILED"
    BACKUP_FAILED = "BACKUP_FAILED"
    RESTORE_INVALID = "RESTORE_INVALID"
    DB_FAILED = "DB_FAILED"
    SYSTEM_PATH = "SYSTEM_PATH"

    @property
    def family(self) -> ErrorFamily:
        return ErrorFamily(self.value.split("_", 1)[0])


class DomainError(Exception):
    """Only deliberate public messages belong here; never raw exception text."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def payload(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class Identifier:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise ValueError("Identifier must contain a UUID.")

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)


class AnalysisId(Identifier):
    """Analysis identity."""


class AnalysisVersionId(Identifier):
    """Version identity."""


class CriterionId(Identifier):
    """Criterion identity."""


class WorkbookArtifactId(Identifier):
    """Workbook identity."""


class PresetId(Identifier):
    """Preset identity."""


class ReportArtifactId(Identifier):
    """Report identity."""


class BackupArtifactId(Identifier):
    """Backup identity."""


def require_text(value: str, field: str) -> None:
    if not value.strip():
        raise DomainError(ErrorCode.VALIDATION_REQUIRED, f"Enter {field}.")


def require_aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise DomainError(ErrorCode.VALIDATION_VALUE, "Timestamp must include a timezone.")


@dataclass(frozen=True)
class AnalysisMetadata:
    id: AnalysisId
    name: str
    created_at: datetime
    description: str = ""

    def __post_init__(self) -> None:
        require_text(self.name, "an analysis name")
        require_aware(self.created_at)


@dataclass(frozen=True)
class VersionMetadata:
    id: AnalysisVersionId
    analysis_id: AnalysisId
    number: int
    status: VersionStatus
    version_type: VersionType
    application_version: str
    created_at: datetime
    change_note: str = ""
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if isinstance(self.number, bool) or self.number < 1:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Version number must be positive.")
        require_text(self.application_version, "an application version")
        require_aware(self.created_at)
        if self.number > 1:
            require_text(self.change_note, "a change note")
        if self.completed_at is not None:
            require_aware(self.completed_at)
            if self.completed_at < self.created_at:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Completion precedes creation.")
