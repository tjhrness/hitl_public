"""Only sanctioned execution path: immutable input lock, atomic results and terminal status."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from inter_rater_analyzer.analytics import WorkbookResult, analyze_workbook
from inter_rater_analyzer.configuration import validate_configuration
from inter_rater_analyzer.continuous import exclude_items
from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.database import Database, Migration, transaction
from inter_rater_analyzer.domain import AnalysisVersionId, DomainError, ErrorCode, RatingType
from inter_rater_analyzer.drafts import DraftService, encode
from inter_rater_analyzer.priority import rank_items
from inter_rater_analyzer.priority_signals import priority_signals
from inter_rater_analyzer.uncertainty import preflight_uncertainty


def permanent_table(name: str) -> tuple[str, ...]:
    return (
        f"CREATE TABLE {name}(version_id TEXT PRIMARY KEY REFERENCES analysis_versions(id), "
        "payload TEXT NOT NULL)",
        f"CREATE TRIGGER {name}_update BEFORE UPDATE ON {name} "
        "BEGIN SELECT RAISE(ABORT,'Execution history is immutable'); END",
        f"CREATE TRIGGER {name}_delete BEFORE DELETE ON {name} "
        "BEGIN SELECT RAISE(ABORT,'Execution history is permanent'); END",
        f"CREATE TRIGGER {name}_draft BEFORE INSERT ON {name} "
        "WHEN (SELECT status FROM analysis_versions WHERE id=NEW.version_id)!='Draft' "
        "BEGIN SELECT RAISE(ABORT,'Execution requires a Draft'); END",
    )


EXECUTION_MIGRATION = Migration(
    6,
    (
        *permanent_table("execution_snapshots"),
        *permanent_table("execution_results"),
        *permanent_table("execution_failures"),
        "CREATE TRIGGER execution_draft_lock BEFORE UPDATE ON drafts "
        "WHEN EXISTS(SELECT 1 FROM execution_snapshots WHERE version_id=OLD.version_id) "
        "BEGIN SELECT RAISE(ABORT,'Execution configuration is locked'); END",
        "CREATE TRIGGER execution_artifact_lock BEFORE INSERT ON workbook_artifacts "
        "WHEN EXISTS(SELECT 1 FROM execution_snapshots WHERE version_id=NEW.version_id) "
        "BEGIN SELECT RAISE(ABORT,'Execution workbook is locked'); END",
        "CREATE TRIGGER execution_note_lock BEFORE UPDATE OF change_note ON analysis_versions "
        "WHEN EXISTS(SELECT 1 FROM execution_snapshots WHERE version_id=OLD.id) "
        "BEGIN SELECT RAISE(ABORT,'Execution metadata is locked'); END",
        "CREATE TRIGGER completed_requires_results BEFORE UPDATE ON analysis_versions "
        "WHEN NEW.status='Completed' AND NOT EXISTS(SELECT 1 FROM execution_results "
        "WHERE version_id=NEW.id) "
        "BEGIN SELECT RAISE(ABORT,'Completed version requires results'); END",
        "CREATE TRIGGER results_require_snapshot BEFORE INSERT ON execution_results "
        "WHEN NOT EXISTS(SELECT 1 FROM execution_snapshots WHERE version_id=NEW.version_id) "
        "BEGIN SELECT RAISE(ABORT,'Results require locked input'); END",
    ),
)


@dataclass(frozen=True)
class ExecutionService:
    database: Database
    drafts: DraftService

    def execute(
        self,
        version_id: AnalysisVersionId,
        *,
        progress: Callable[[str], None] | None = None,
        worker_processes: bool = False,
    ) -> WorkbookResult:
        if progress:
            progress("Validating and checking selected metrics")
        state = self.drafts.active()
        if state is None or state.version_id != version_id:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Select the active Draft.")
        config = state.configuration
        if config is None or state.workbook_id is None or not state.types_locked:
            raise DomainError(
                ErrorCode.VALIDATION_REQUIRED, "Confirm workbook types and configuration."
            )
        imported = self.drafts.workbooks.load(state.workbook_id)
        data = imported.assign_types({c.name: c.rating_type for c in config.criteria})
        validate_configuration(config, data)
        if any(
            c.rating_type in (RatingType.BINARY, RatingType.NOMINAL)
            and "raw_agreement" not in c.metrics
            for c in config.criteria
        ):
            raise DomainError(
                ErrorCode.VALIDATION_REQUIRED,
                "Binary and nominal criteria require raw percentage agreement.",
            )
        excluded = {item.item_id for item in config.exclusions}
        included = tuple(replace(exclude_items(d, excluded), findings=()) for d in data)
        warnings = {w.code for d in included for w in quality_warnings(d)}
        if not warnings <= set(state.acknowledged_warnings):
            raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Acknowledge all current warnings.")
        settings = {c.name: c for c in config.criteria}
        for criterion in included:
            findings = preflight_uncertainty(criterion, settings[criterion.name])
            if findings:
                raise DomainError(ErrorCode.STAT_UNDEFINED, findings[0].message)
        rank_items(tuple(priority_signals(d, settings[d.name]) for d in included), config.weights)
        payload = encode(state)
        # Statistical seed identity depends on inputs/configuration, not random version UUID.
        seed_input = json.dumps(
            {"data": [asdict(d) for d in included], "configuration": asdict(config)},
            default=str,
            sort_keys=True,
        )
        seed_key = hashlib.sha256(seed_input.encode()).hexdigest()
        with self.database.connection() as conn, transaction(conn):
            row = conn.execute(
                "SELECT payload FROM drafts WHERE version_id=?", (str(version_id),)
            ).fetchone()
            if row is None or row[0] != payload:
                raise DomainError(
                    ErrorCode.VALIDATION_VALUE, "Draft changed; review and execute again."
                )
            conn.execute("INSERT INTO execution_snapshots VALUES(?,?)", (str(version_id), payload))
        try:
            if progress:
                progress("Computing metrics, uncertainty, diagnostics and priorities")
            result = analyze_workbook(
                data, config, version_key=seed_key, worker_processes=worker_processes
            )
            snapshot = json.dumps(
                {
                    "result": asdict(result),
                    "data": [asdict(d) for d in included],
                    "all_data": [asdict(d) for d in data],
                    "configuration": asdict(config),
                    "seed_key": seed_key,
                },
                default=str,
                sort_keys=True,
                allow_nan=False,
            )
            with self.database.connection() as conn, transaction(conn):
                if progress:
                    progress("Saving complete results")
                conn.execute(
                    "INSERT INTO execution_results VALUES(?,?)", (str(version_id), snapshot)
                )
                conn.execute(
                    "UPDATE analysis_versions SET status='Completed',completed_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), str(version_id)),
                )
            return result
        except Exception as error:
            # Exception text and traceback locals may contain identities.
            # Retain only safe diagnostics.
            failure = json.dumps(
                {
                    "code": "STAT_UNDEFINED",
                    "stage": "execution",
                    "exception_type": type(error).__name__,
                    "message": "Analysis failed; no partial results were saved.",
                }
            )
            with self.database.connection() as conn, transaction(conn):
                conn.execute(
                    "INSERT INTO execution_failures VALUES(?,?)", (str(version_id), failure)
                )
                conn.execute(
                    "UPDATE analysis_versions SET status='Failed',completed_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), str(version_id)),
                )
            raise DomainError(
                ErrorCode.STAT_UNDEFINED, "Analysis failed; no partial results were saved."
            ) from None

    def load(self, version_id: AnalysisVersionId) -> dict[str, Any]:
        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT r.payload FROM execution_results r JOIN analysis_versions v "
                "ON v.id=r.version_id WHERE r.version_id=? AND v.status='Completed'",
                (str(version_id),),
            ).fetchone()
        if row is None:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "No completed results for this version.")
        return json.loads(row[0])

    def recover_interrupted(self) -> None:
        """Only call with exclusive application ownership, before resuming UI state."""
        with self.database.connection() as conn, transaction(conn):
            rows = conn.execute(
                "SELECT v.id FROM analysis_versions v JOIN execution_snapshots s "
                "ON s.version_id=v.id WHERE v.status='Draft'"
            ).fetchall()
            for row in rows:
                failure = json.dumps(
                    {
                        "code": "EXECUTION_INTERRUPTED",
                        "stage": "execution",
                        "message": "Previous execution was interrupted; "
                        "no partial results are available.",
                    }
                )
                conn.execute("INSERT INTO execution_failures VALUES(?,?)", (row[0], failure))
                conn.execute(
                    "UPDATE analysis_versions SET status='Failed',completed_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), row[0]),
                )
