"""One active Draft, atomic autosaves, typed restart-safe configuration."""

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path

from inter_rater_analyzer.analyses import AnalysisRepository
from inter_rater_analyzer.configuration import (
    AnalysisConfiguration,
    CriterionConfiguration,
    Exclusion,
    PrioritySignal,
    SignalWeight,
)
from inter_rater_analyzer.database import Database, Migration, transaction
from inter_rater_analyzer.domain import (
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    PresetId,
    RatingType,
    VersionStatus,
    WorkbookArtifactId,
)
from inter_rater_analyzer.workbooks import ImportedWorkbook, WorkbookService

DRAFT_MIGRATION = Migration(
    5,
    (
        "CREATE UNIQUE INDEX one_draft ON analysis_versions(status) WHERE status='Draft'",
        "CREATE TABLE drafts(version_id TEXT PRIMARY KEY REFERENCES analysis_versions(id), "
        "payload TEXT NOT NULL DEFAULT '{}')",
        "CREATE TRIGGER draft_creation AFTER INSERT ON analysis_versions "
        "WHEN NEW.status='Draft' BEGIN INSERT INTO drafts(version_id) VALUES(NEW.id); END",
        "INSERT INTO drafts(version_id) SELECT id FROM analysis_versions WHERE status='Draft'",
        "CREATE TRIGGER draft_immutable BEFORE UPDATE ON drafts "
        "WHEN (SELECT status FROM analysis_versions WHERE id=OLD.version_id)!='Draft' "
        "BEGIN SELECT RAISE(ABORT,'Terminal Draft cannot be changed'); END",
        "CREATE TRIGGER draft_permanent BEFORE DELETE ON drafts "
        "BEGIN SELECT RAISE(ABORT,'Draft history is permanent'); END",
    ),
)


@dataclass(frozen=True)
class DraftState:
    version_id: AnalysisVersionId
    workbook_id: WorkbookArtifactId | None = None
    preset_id: PresetId | None = None
    configuration: AnalysisConfiguration | None = None
    acknowledged_warnings: tuple[str, ...] = ()
    types_locked: bool = False


def encode(state: DraftState) -> str:
    return json.dumps(
        {
            "workbook_id": str(state.workbook_id) if state.workbook_id else None,
            "preset_id": str(state.preset_id) if state.preset_id else None,
            "configuration": asdict(state.configuration) if state.configuration else None,
            "acknowledged_warnings": state.acknowledged_warnings,
            "types_locked": state.types_locked,
        },
        default=str,
        sort_keys=True,
        allow_nan=False,
    )


def decode(version_id: AnalysisVersionId, payload: str) -> DraftState:
    values = json.loads(payload)
    raw = values.get("configuration")
    configuration = None
    if raw is not None:
        configuration = AnalysisConfiguration(
            tuple(
                CriterionConfiguration(
                    c["name"],
                    RatingType(c["rating_type"]),
                    tuple(c["ordinal_order"]),
                    c["tolerance"],
                    tuple(c["metrics"]),
                )
                for c in raw["criteria"]
            ),
            raw["confidence"],
            raw["alpha"],
            tuple(Exclusion(e["item_id"], e["reason"]) for e in raw["exclusions"]),
            tuple(
                SignalWeight(PrioritySignal(w["signal"]), Decimal(w["weight"]))
                for w in raw["weights"]
            ),
        )
    return DraftState(
        version_id,
        WorkbookArtifactId.parse(values["workbook_id"]) if values.get("workbook_id") else None,
        PresetId.parse(values["preset_id"]) if values.get("preset_id") else None,
        configuration,
        tuple(values.get("acknowledged_warnings", [])),
        values.get("types_locked", False),
    )


@dataclass(frozen=True)
class DraftService:
    database: Database
    analyses: AnalysisRepository
    workbooks: WorkbookService

    def attach_workbook(self, source: Path) -> ImportedWorkbook:
        state = self.active()
        if state is None:
            raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Create a Draft first.")
        if state.types_locked:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Workbook is locked after type confirmation."
            )
        imported = self.workbooks.import_workbook(state.version_id, source)
        self.save(
            replace(
                state,
                workbook_id=imported.inspection.artifact_id,
                configuration=None,
                acknowledged_warnings=(),
            )
        )
        return imported

    def resume_workbook(self) -> ImportedWorkbook | None:
        state = self.active()
        return self.workbooks.load(state.workbook_id) if state and state.workbook_id else None

    def create(self, name: str, description: str = "") -> DraftState:
        try:
            _, version = self.analyses.create(name, description)
        except sqlite3.IntegrityError as error:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Resume or abandon the existing Draft first."
            ) from error
        return DraftState(version.id)

    def active(self) -> DraftState | None:
        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT d.version_id,d.payload FROM drafts d "
                "JOIN analysis_versions v ON v.id=d.version_id WHERE v.status='Draft'"
            ).fetchone()
        return decode(AnalysisVersionId.parse(row[0]), row[1]) if row else None

    def save(self, state: DraftState) -> None:
        payload = encode(state)
        with self.database.connection() as conn, transaction(conn):
            saved = conn.execute(
                "SELECT payload FROM drafts WHERE version_id=?", (str(state.version_id),)
            ).fetchone()
            if saved is not None:
                old = decode(state.version_id, saved[0])
                if old.types_locked and (
                    not state.types_locked
                    or old.workbook_id != state.workbook_id
                    or state.configuration is None
                    or old.configuration is None
                    or {c.name: c.rating_type for c in old.configuration.criteria}
                    != {c.name: c.rating_type for c in state.configuration.criteria}
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION_VALUE, "Confirmed rating types are locked."
                    )
            if state.workbook_id is not None:
                row = conn.execute(
                    "SELECT a.version_id, source.analysis_id, target.analysis_id, "
                    "target.version_type FROM workbook_artifacts a "
                    "JOIN analysis_versions source ON source.id=a.version_id "
                    "JOIN analysis_versions target ON target.id=? WHERE a.id=?",
                    (str(state.version_id), str(state.workbook_id)),
                ).fetchone()
                if row is None or (
                    row[0] != str(state.version_id)
                    and not (row[1] == row[2] and row[3] == "Configuration Only")
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION_VALUE, "Workbook does not belong to Draft."
                    )
            cursor = conn.execute(
                "UPDATE drafts SET payload=? WHERE version_id=? AND "
                "EXISTS(SELECT 1 FROM analysis_versions WHERE id=? AND status='Draft')",
                (payload, str(state.version_id), str(state.version_id)),
            )
            if cursor.rowcount != 1:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Only the active Draft can be saved.")

    def abandon(self, version_id: AnalysisVersionId) -> None:
        self.analyses.finish(version_id, VersionStatus.ABANDONED)
