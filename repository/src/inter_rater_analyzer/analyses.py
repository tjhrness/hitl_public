"""Analysis/version repository with transactional numbering and immutability."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from inter_rater_analyzer.config import APPLICATION_VERSION
from inter_rater_analyzer.database import Database, Migration, transaction
from inter_rater_analyzer.domain import (
    AnalysisId,
    AnalysisMetadata,
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    VersionMetadata,
    VersionStatus,
    VersionType,
    require_text,
)

ANALYSIS_MIGRATION = Migration(
    2,
    (
        "CREATE TABLE analyses(id TEXT PRIMARY KEY, "
        "name TEXT NOT NULL CHECK(length(trim(name))>0), "
        "description TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE TABLE analysis_versions(id TEXT PRIMARY KEY, "
        "analysis_id TEXT NOT NULL REFERENCES analyses(id), "
        "number INTEGER NOT NULL CHECK(number>=1), status TEXT NOT NULL "
        "CHECK(status IN ('Draft','Completed','Failed','Abandoned')), version_type TEXT NOT NULL "
        "CHECK(version_type IN ('Data Change','Configuration Only')), change_note TEXT NOT NULL, "
        "application_version TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, "
        "UNIQUE(analysis_id,number), CHECK(number=1 OR length(trim(change_note))>0))",
        "CREATE TRIGGER immutable_version_update BEFORE UPDATE ON analysis_versions "
        "WHEN OLD.status!='Draft' BEGIN SELECT RAISE(ABORT,'Terminal version is immutable'); END",
        "CREATE TRIGGER immutable_version_delete BEFORE DELETE ON analysis_versions "
        "BEGIN SELECT RAISE(ABORT,'Versions are permanent'); END",
    ),
)


def version_from_row(row: sqlite3.Row) -> VersionMetadata:
    return VersionMetadata(
        AnalysisVersionId.parse(row["id"]),
        AnalysisId.parse(row["analysis_id"]),
        row["number"],
        VersionStatus(row["status"]),
        VersionType(row["version_type"]),
        row["application_version"],
        datetime.fromisoformat(row["created_at"]),
        row["change_note"],
        datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def insert_version(conn: sqlite3.Connection, version: VersionMetadata) -> None:
    conn.execute(
        "INSERT INTO analysis_versions VALUES(?,?,?,?,?,?,?,?,?)",
        (
            str(version.id),
            str(version.analysis_id),
            version.number,
            version.status.value,
            version.version_type.value,
            version.change_note,
            version.application_version,
            version.created_at.isoformat(),
            version.completed_at.isoformat() if version.completed_at else None,
        ),
    )


@dataclass(frozen=True)
class AnalysisRepository:
    database: Database

    def create(self, name: str, description: str = "") -> tuple[AnalysisMetadata, VersionMetadata]:
        now = datetime.now(UTC)
        analysis = AnalysisMetadata(AnalysisId.new(), name.strip(), now, description)
        version = VersionMetadata(
            AnalysisVersionId.new(),
            analysis.id,
            1,
            VersionStatus.DRAFT,
            VersionType.DATA_CHANGE,
            APPLICATION_VERSION,
            now,
        )
        with self.database.connection() as conn, transaction(conn):
            conn.execute(
                "INSERT INTO analyses VALUES(?,?,?,?)",
                (str(analysis.id), analysis.name, description, now.isoformat()),
            )
            insert_version(conn, version)
        return analysis, version

    def new_version(self, analysis_id: AnalysisId, kind: VersionType, note: str) -> VersionMetadata:
        require_text(note, "a change note")
        with self.database.connection() as conn, transaction(conn):
            row = conn.execute(
                "SELECT MAX(number) FROM analysis_versions WHERE analysis_id=?", (str(analysis_id),)
            ).fetchone()
            if row is None or row[0] is None:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Analysis does not exist.")
            version = VersionMetadata(
                AnalysisVersionId.new(),
                analysis_id,
                int(row[0]) + 1,
                VersionStatus.DRAFT,
                kind,
                APPLICATION_VERSION,
                datetime.now(UTC),
                note.strip(),
            )
            insert_version(conn, version)
        return version

    def get_version(self, identifier: AnalysisVersionId) -> VersionMetadata:
        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_versions WHERE id=?", (str(identifier),)
            ).fetchone()
            if row is None:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Version does not exist.")
            return version_from_row(row)

    def update_draft_note(self, identifier: AnalysisVersionId, note: str) -> None:
        with self.database.connection() as conn, transaction(conn):
            row = conn.execute(
                "SELECT number FROM analysis_versions WHERE id=? AND status=?",
                (str(identifier), VersionStatus.DRAFT.value),
            ).fetchone()
            if row is None:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Only a Draft can be updated.")
            if int(row[0]) > 1:
                require_text(note, "a change note")
            conn.execute(
                "UPDATE analysis_versions SET change_note=? WHERE id=?",
                (note.strip(), str(identifier)),
            )

    def finish(self, identifier: AnalysisVersionId, status: VersionStatus) -> None:
        if status is VersionStatus.COMPLETED:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Use the execution service to complete a version."
            )
        if status is VersionStatus.DRAFT:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Choose a terminal status.")
        with self.database.connection() as conn, transaction(conn):
            cursor = conn.execute(
                "UPDATE analysis_versions SET status=?, completed_at=? "
                "WHERE id=? AND status='Draft'",
                (status.value, datetime.now(UTC).isoformat(), str(identifier)),
            )
            if cursor.rowcount != 1:
                raise DomainError(ErrorCode.VALIDATION_VALUE, "Only a Draft can be finalized.")
