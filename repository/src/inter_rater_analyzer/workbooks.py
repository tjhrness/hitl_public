"""Draft workbook import orchestration."""

from dataclasses import dataclass, replace
from pathlib import Path

from inter_rater_analyzer.analyses import AnalysisRepository
from inter_rater_analyzer.artifacts import ArtifactStore
from inter_rater_analyzer.canonical import WorkbookDataset, canonicalize
from inter_rater_analyzer.configuration import AnalysisConfiguration, validate_configuration
from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.domain import (
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    RatingType,
    WorkbookArtifactId,
)
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.identity import Criterion, MappingRepository
from inter_rater_analyzer.ingestion import (
    WorkbookInspection,
    extract_workbook,
    inspect_workbook,
)
from inter_rater_analyzer.ratings import NormalizedCriterion, normalize_ratings
from inter_rater_analyzer.validation import validate_structure


@dataclass(frozen=True)
class ImportedWorkbook:
    inspection: WorkbookInspection
    dataset: WorkbookDataset | None
    findings: tuple[ValidationFinding, ...] = ()

    def configure(self, config: AnalysisConfiguration) -> AnalysisConfiguration:
        data = self.assign_types({c.name: c.rating_type for c in config.criteria})
        return validate_configuration(config, data)

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        return self.dataset.criteria if self.dataset else ()

    def assign_types(self, types: dict[str, RatingType]) -> tuple[NormalizedCriterion, ...]:
        if self.dataset is None:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Resolve workbook findings first.")
        if set(types) != set(self.dataset.criterion_names):
            raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Select a type for every criterion.")
        normalized = tuple(
            normalize_ratings(criterion, types[criterion.name]) for criterion in self.criteria
        )
        return tuple(
            replace(data, findings=data.findings + quality_warnings(data)) for data in normalized
        )


@dataclass(frozen=True)
class WorkbookService:
    artifacts: ArtifactStore
    analyses: AnalysisRepository
    mappings: MappingRepository

    def import_workbook(self, version_id: AnalysisVersionId, source: Path) -> ImportedWorkbook:
        inspection = inspect_workbook(source, validate_count=False)
        artifact = self.artifacts.import_workbook(version_id, source)
        if artifact.sha256 != inspection.sha256:
            raise DomainError(
                ErrorCode.FILE_INVALID, "Workbook changed during import. Import again."
            )
        return self.load(artifact.id)

    def load(self, artifact_id: WorkbookArtifactId) -> ImportedWorkbook:
        artifact = self.artifacts.get(artifact_id)
        if not self.artifacts.verify(artifact):
            raise DomainError(ErrorCode.FILE_INVALID, "Stored workbook failed its integrity check.")
        inspection = inspect_workbook(artifact.path, validate_count=False)
        public_inspection = WorkbookInspection(artifact.sha256, inspection.worksheets, artifact.id)
        findings: list[ValidationFinding] = []
        raw = extract_workbook(artifact.path, findings)
        findings.extend(validate_structure(raw))
        if findings:
            return ImportedWorkbook(public_inspection, None, tuple(findings))
        dataset, mapping = canonicalize(raw)
        analysis_id = self.analyses.get_version(artifact.version_id).analysis_id
        self.mappings.preserve(analysis_id, mapping)
        return ImportedWorkbook(
            WorkbookInspection(artifact.sha256, inspection.worksheets, artifact.id),
            dataset,
        )
