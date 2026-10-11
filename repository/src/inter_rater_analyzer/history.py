"""Public history projections contain analysis metadata and aliases only."""

from dataclasses import dataclass

from inter_rater_analyzer.database import Database
from inter_rater_analyzer.domain import AnalysisVersionId


@dataclass(frozen=True)
class HistoryEntry:
    version_id: AnalysisVersionId
    name: str
    number: int
    status: str
    version_type: str
    change_note: str


@dataclass(frozen=True)
class HistoryService:
    database: Database

    def list(self) -> tuple[HistoryEntry, ...]:
        with self.database.connection() as conn:
            rows = conn.execute(
                "SELECT v.id,a.name,v.number,v.status,v.version_type,v.change_note "
                "FROM analysis_versions v JOIN analyses a ON a.id=v.analysis_id "
                "ORDER BY a.created_at DESC,v.number DESC"
            ).fetchall()
        return tuple(HistoryEntry(AnalysisVersionId.parse(r[0]), *tuple(r)[1:]) for r in rows)
