"""Managed artifacts: original-byte hashing, atomic writes, protected metadata."""

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

from inter_rater_analyzer.config import RuntimePaths
from inter_rater_analyzer.database import Database, Migration, transaction
from inter_rater_analyzer.domain import (
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    WorkbookArtifactId,
)

ARTIFACT_MIGRATION = Migration(
    3,
    (
        "CREATE TABLE workbook_artifacts(id TEXT PRIMARY KEY, "
        "version_id TEXT NOT NULL REFERENCES analysis_versions(id), path TEXT NOT NULL UNIQUE, "
        "sha256 TEXT NOT NULL, original_filename TEXT NOT NULL)",
        "CREATE TRIGGER immutable_artifact_update BEFORE UPDATE ON workbook_artifacts "
        "BEGIN SELECT RAISE(ABORT,'Artifacts are immutable'); END",
        "CREATE TRIGGER immutable_artifact_delete BEFORE DELETE ON workbook_artifacts "
        "BEGIN SELECT RAISE(ABORT,'Artifacts are permanent'); END",
        "CREATE TRIGGER artifact_draft_only BEFORE INSERT ON workbook_artifacts "
        "WHEN (SELECT status FROM analysis_versions WHERE id=NEW.version_id)!='Draft' "
        "BEGIN SELECT RAISE(ABORT,'Only Draft workbooks can be imported'); END",
    ),
)


def sanitize_filename(name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")[:120]
    value = value.rstrip(". ") or "artifact"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", value.split(".")[0]):
        value = "_" + value
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        with NamedTemporaryFile(dir=target.parent, prefix=".stage-", delete=False) as stream:
            staging = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, target)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


@dataclass(frozen=True)
class WorkbookArtifact:
    """Internal persistence object; original filename is not a public projection."""

    id: WorkbookArtifactId
    version_id: AnalysisVersionId
    path: Path
    sha256: str
    original_filename: str = field(repr=False)


@dataclass(frozen=True)
class ArtifactStore:
    paths: RuntimePaths
    database: Database

    def import_workbook(self, version_id: AnalysisVersionId, source: Path) -> WorkbookArtifact:
        target: Path | None = None
        try:
            with self.database.connection() as conn, transaction(conn):
                row = conn.execute(
                    "SELECT status FROM analysis_versions WHERE id=?", (str(version_id),)
                ).fetchone()
                if row is None or row[0] != "Draft":
                    raise DomainError(
                        ErrorCode.VALIDATION_VALUE, "Import requires a Draft version."
                    )
                data = source.read_bytes()
                identifier = WorkbookArtifactId.new()
                target = self.paths.workbooks / f"{identifier}.xlsx"
                artifact = WorkbookArtifact(
                    identifier, version_id, target, sha256(data), source.name
                )
                atomic_write(target, data)
                conn.execute(
                    "INSERT INTO workbook_artifacts VALUES(?,?,?,?,?)",
                    (
                        str(identifier),
                        str(version_id),
                        str(target.relative_to(self.paths.root)),
                        artifact.sha256,
                        source.name,
                    ),
                )
            return artifact
        except BaseException as error:
            if target is not None:
                target.unlink(missing_ok=True)
            if isinstance(error, OSError):
                raise DomainError(
                    ErrorCode.FILE_INVALID,
                    "Cannot copy workbook. Check file access and disk space.",
                ) from error
            raise

    def get(self, identifier: WorkbookArtifactId) -> WorkbookArtifact:
        with self.database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM workbook_artifacts WHERE id=?", (str(identifier),)
            ).fetchone()
        if row is None:
            raise DomainError(ErrorCode.FILE_INVALID, "Workbook artifact does not exist.")
        path = (self.paths.root / row["path"]).resolve()
        if not path.is_relative_to(self.paths.workbooks.resolve()):
            raise DomainError(ErrorCode.FILE_INVALID, "Workbook storage path is invalid.")
        return WorkbookArtifact(
            identifier,
            AnalysisVersionId.parse(row["version_id"]),
            path,
            row["sha256"],
            row["original_filename"],
        )

    def verify(self, artifact: WorkbookArtifact) -> bool:
        try:
            return sha256(artifact.path.read_bytes()) == artifact.sha256
        except OSError:
            return False
