"""New-version workflow with compatibility checked before version creation."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from inter_rater_analyzer.canonical import canonicalize
from inter_rater_analyzer.configuration import AnalysisConfiguration
from inter_rater_analyzer.domain import (
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    VersionStatus,
    VersionType,
    require_text,
)
from inter_rater_analyzer.drafts import DraftService, DraftState, decode
from inter_rater_analyzer.ingestion import extract_workbook, inspect_workbook
from inter_rater_analyzer.validation import validate_structure
from inter_rater_analyzer.workbooks import ImportedWorkbook


@dataclass(frozen=True)
class VersionService:
    drafts: DraftService

    def create(
        self,
        previous_id: AnalysisVersionId,
        kind: VersionType,
        note: str,
        *,
        source: Path | None = None,
        configuration: AnalysisConfiguration | None = None,
    ) -> DraftState:
        require_text(note, "a change note")
        if self.drafts.active() is not None:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Resume or abandon the active Draft first."
            )
        previous = self.drafts.analyses.get_version(previous_id)
        if previous.status not in (VersionStatus.COMPLETED, VersionStatus.FAILED):
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Choose a Completed or Failed version.")
        with self.drafts.database.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM drafts WHERE version_id=?", (str(previous_id),)
            ).fetchone()
            latest = conn.execute(
                "SELECT MAX(number) FROM analysis_versions WHERE analysis_id=?",
                (str(previous.analysis_id),),
            ).fetchone()[0]
        if row is None or previous.number != latest:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Create a version from the latest version."
            )
        old = decode(previous_id, row[0])
        if old.workbook_id is None or old.configuration is None:
            raise DomainError(
                ErrorCode.VALIDATION_REQUIRED, "Previous version has no configured workbook."
            )
        config = configuration or old.configuration
        if {c.name: c.rating_type for c in config.criteria} != {
            c.name: c.rating_type for c in old.configuration.criteria
        }:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Keep the same criterion names and rating types."
            )
        baseline = self.drafts.workbooks.load(old.workbook_id)
        if baseline.dataset is None:
            raise DomainError(ErrorCode.FILE_INVALID, "Stored baseline workbook is invalid.")
        with TemporaryDirectory(dir=self.drafts.workbooks.artifacts.paths.temp) as directory:
            staged: Path | None = None
            if kind is VersionType.DATA_CHANGE:
                if source is None:
                    raise DomainError(
                        ErrorCode.VALIDATION_REQUIRED, "Select a replacement workbook."
                    )
                staged = Path(directory) / "replacement.xlsx"
                staged.write_bytes(source.read_bytes())
                inspection = inspect_workbook(staged)
                raw = extract_workbook(staged)
                findings = validate_structure(raw)
                if findings:
                    raise DomainError(ErrorCode.VALIDATION_VALUE, findings[0].message)
                dataset, mappings = canonicalize(raw)
                if set(dataset.criterion_names) != set(baseline.dataset.criterion_names):
                    raise DomainError(ErrorCode.VALIDATION_VALUE, "Keep the exact worksheet names.")
                if dataset.item_ids != baseline.dataset.item_ids:
                    raise DomainError(
                        ErrorCode.VALIDATION_VALUE, "Keep the same normalized Item ID set."
                    )
                self.drafts.workbooks.mappings.preserve(previous.analysis_id, mappings)
                ImportedWorkbook(inspection, dataset).configure(config)
            elif source is not None:
                raise DomainError(
                    ErrorCode.VALIDATION_VALUE, "Configuration Only reuses the stored workbook."
                )
            else:
                baseline.configure(config)
            version = self.drafts.analyses.new_version(previous.analysis_id, kind, note)
            try:
                workbook_id = old.workbook_id
                if staged is not None:
                    workbook_id = self.drafts.workbooks.import_workbook(
                        version.id, staged
                    ).inspection.artifact_id
                state = replace(
                    old,
                    version_id=version.id,
                    workbook_id=workbook_id,
                    configuration=config,
                    types_locked=True,
                    acknowledged_warnings=(),
                )
                self.drafts.save(state)
                return state
            except Exception:
                self.drafts.analyses.finish(version.id, VersionStatus.ABANDONED)
                raise
