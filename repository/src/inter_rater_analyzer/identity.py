"""Canonical identity normalization and protected rater mapping persistence."""

from dataclasses import dataclass, field

from inter_rater_analyzer.database import Database, Migration, transaction
from inter_rater_analyzer.domain import AnalysisId, DomainError, ErrorCode
from inter_rater_analyzer.ingestion import RawCriterion

MAPPING_MIGRATION = Migration(
    4,
    (
        "CREATE TABLE rater_mappings(analysis_id TEXT NOT NULL REFERENCES analyses(id), "
        "position INTEGER NOT NULL, original TEXT NOT NULL, normalized TEXT NOT NULL, "
        "alias TEXT NOT NULL, PRIMARY KEY(analysis_id,position), UNIQUE(analysis_id,normalized))",
        "CREATE TRIGGER mapping_immutable BEFORE UPDATE ON rater_mappings "
        "BEGIN SELECT RAISE(ABORT,'Rater mappings are immutable'); END",
    ),
)


@dataclass(frozen=True)
class RaterMapping:
    position: int
    original: str = field(repr=False)
    normalized: str = field(repr=False)
    alias: str


@dataclass(frozen=True)
class RatingRow:
    excel_row: int
    item_id: str
    ratings: tuple[object, ...]


@dataclass(frozen=True)
class Criterion:
    name: str
    raters: tuple[str, ...]
    rows: tuple[RatingRow, ...]


def normalize_criterion(raw: RawCriterion) -> tuple[Criterion, tuple[RaterMapping, ...]]:
    mappings: list[RaterMapping] = []
    seen: set[str] = set()
    if len(raw.rater_headers) > 10:
        raise DomainError(ErrorCode.VALIDATION_VALUE, "Use at most 10 raters.")
    for position, header in enumerate(raw.rater_headers):
        original = header[len("Rater:") :].strip()
        normalized = original.casefold()
        if not normalized or normalized in seen:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Rater identities must be nonblank and unique."
            )
        seen.add(normalized)
        mappings.append(RaterMapping(position, original, normalized, f"Rater {chr(65 + position)}"))
    rows: list[RatingRow] = []
    seen.clear()
    for row in raw.rows:
        item_id = str(row.item_id).strip() if row.item_id is not None else ""
        if not item_id or item_id in seen:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Item IDs must be nonblank and unique.")
        seen.add(item_id)
        rows.append(RatingRow(row.excel_row, item_id, row.ratings))
    return Criterion(raw.name, tuple(m.alias for m in mappings), tuple(rows)), tuple(mappings)


@dataclass(frozen=True)
class MappingRepository:
    database: Database

    def preserve(self, analysis_id: AnalysisId, mappings: tuple[RaterMapping, ...]) -> None:
        with self.database.connection() as conn, transaction(conn):
            existing = tuple(
                row[0]
                for row in conn.execute(
                    "SELECT normalized FROM rater_mappings WHERE analysis_id=? ORDER BY position",
                    (str(analysis_id),),
                )
            )
            if existing:
                if existing != tuple(mapping.normalized for mapping in mappings):
                    raise DomainError(
                        ErrorCode.VALIDATION_VALUE, "Use the same raters in the same column order."
                    )
                return
            conn.executemany(
                "INSERT INTO rater_mappings VALUES(?,?,?,?,?)",
                (
                    (str(analysis_id), m.position, m.original, m.normalized, m.alias)
                    for m in mappings
                ),
            )
