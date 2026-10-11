import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from inter_rater_analyzer.domain import (
    AnalysisId,
    AnalysisMetadata,
    AnalysisVersionId,
    BackupArtifactId,
    BackupType,
    CriterionId,
    DomainError,
    ErrorCode,
    ErrorFamily,
    MetricScope,
    PresetId,
    RatingType,
    ReportArtifactId,
    ValidationSeverity,
    VersionMetadata,
    VersionStatus,
    VersionType,
    WorkbookArtifactId,
)


@pytest.mark.parametrize(
    "kind",
    [
        RatingType,
        VersionStatus,
        VersionType,
        ValidationSeverity,
        MetricScope,
        BackupType,
        ErrorFamily,
    ],
)
def test_enum_serialization(kind):
    for member in kind:
        assert kind(json.loads(json.dumps(member))) is member


@pytest.mark.parametrize(
    "kind",
    [
        AnalysisId,
        AnalysisVersionId,
        CriterionId,
        WorkbookArtifactId,
        PresetId,
        ReportArtifactId,
        BackupArtifactId,
    ],
)
def test_ids(kind):
    identifier = kind.new()
    assert kind.parse(str(identifier)) == identifier
    assert identifier != kind.new()
    with pytest.raises(ValueError):
        kind.parse("invalid")


def test_ids_are_distinct_types():
    identifier = AnalysisId.new()
    assert identifier != AnalysisVersionId.parse(str(identifier))


def test_metadata_validation_and_immutability():
    now = datetime.now(UTC)
    metadata = AnalysisMetadata(AnalysisId.new(), "Study", now)
    with pytest.raises(FrozenInstanceError):
        metadata.name = "Other"
    with pytest.raises(DomainError):
        AnalysisMetadata(metadata.id, "  ", now)
    with pytest.raises(DomainError):
        AnalysisMetadata(metadata.id, "Study", datetime(2026, 1, 1))
    for number in [0, -1, True]:
        with pytest.raises(DomainError):
            VersionMetadata(
                AnalysisVersionId.new(),
                metadata.id,
                number,
                VersionStatus.DRAFT,
                VersionType.DATA_CHANGE,
                "0.1.0",
                now,
            )
    with pytest.raises(DomainError):
        VersionMetadata(
            AnalysisVersionId.new(),
            metadata.id,
            2,
            VersionStatus.DRAFT,
            VersionType.DATA_CHANGE,
            "0.1.0",
            now,
        )


def test_error_payload():
    error = DomainError(ErrorCode.VALIDATION_REQUIRED, "Enter an analysis name.")
    assert error.payload() == {"code": "VALIDATION_REQUIRED", "message": "Enter an analysis name."}
    assert error.code.family is ErrorFamily.VALIDATION
    assert str(error) == "Enter an analysis name."
