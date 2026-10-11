"""Checksummed snapshots and staged replacement; backup history survives restoration."""

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from inter_rater_analyzer.artifacts import atomic_write, sha256
from inter_rater_analyzer.config import APPLICATION_VERSION, RuntimePaths
from inter_rater_analyzer.database import Database
from inter_rater_analyzer.domain import DomainError, ErrorCode


@dataclass(frozen=True)
class BackupEntry:
    path: Path
    timestamp: str
    kind: str
    version: str
    size: int
    integrity: str


@dataclass(frozen=True)
class RestorePlan:
    payload: bytes
    safety: BackupEntry
    state_digest: str


def replace_directory(source: Path, target: Path) -> None:
    os.replace(source, target)


def recover_restore(root: Path) -> None:
    """Recover a interrupted directory swap before opening or creating a database."""
    root = root.resolve()
    journal = root.parent / f".{root.name}-restore.json"
    if not journal.exists():
        return
    record = json.loads(journal.read_text(encoding="utf-8"))
    paths: list[Path] = []
    for kind in ("restore", "rollback"):
        path = root.parent / record[kind]
        if path.resolve().parent != root.parent or not path.name.startswith(
            f".{root.name}-{kind}-"
        ):
            raise ValueError("Invalid recovery path")
        paths.append(path)
    stage, rollback = paths
    if not root.exists():
        if not rollback.is_dir():
            raise ValueError("Previous state unavailable; retain recovery files")
        replace_directory(rollback, root)
    for path in (stage, rollback):
        if path.exists():
            shutil.rmtree(path)
    journal.unlink()


def _validate(payload: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    with ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("Duplicate archive names")
        if sum(info.file_size for info in archive.infolist()) > 8 * 1024**3:
            raise ValueError("Backup exceeds supported size")
        for name in names:
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or str(path) != name
                or any(part.endswith((".", " ")) for part in path.parts)
            ):
                raise ValueError("Invalid archive path")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["format"] != 1 or manifest["application_version"] != APPLICATION_VERSION:
            raise ValueError("Incompatible backup")
        if manifest["kind"] not in ("Manual", "Pre-Restore"):
            raise ValueError("Invalid backup type")
        datetime.fromisoformat(manifest["timestamp"])
        hashes = manifest["files"]
        if set(names) != {"manifest.json", *hashes} or "data/analyzer.sqlite3" not in hashes:
            raise ValueError("Incomplete backup")
        files: dict[str, bytes] = {}
        for name, digest in hashes.items():
            if name != "data/analyzer.sqlite3" and not name.startswith(("workbooks/", "reports/")):
                raise ValueError("Unexpected state file")
            data = archive.read(name)
            if sha256(data) != digest:
                raise ValueError("Checksum mismatch")
            files[name] = data
        return manifest, files


def _validate_database(root: Path) -> None:
    with Database(root / "data/analyzer.sqlite3").connection() as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid database")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Broken database references")
        row = conn.execute("SELECT schema_version,application_version FROM app_metadata").fetchone()
        if tuple(row) != (8, APPLICATION_VERSION):
            raise ValueError("Incompatible schema")
        for table, folder in (("workbook_artifacts", "workbooks"), ("report_artifacts", "reports")):
            for row in conn.execute(f"SELECT path,sha256 FROM {table}"):
                path = (root / row[0]).resolve()
                if not path.is_relative_to((root / folder).resolve()):
                    raise ValueError("Invalid artifact reference")
                if sha256(path.read_bytes()) != row[1]:
                    raise ValueError("Missing or invalid referenced artifact")


def _stage(files: dict[str, bytes], root: Path) -> None:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _validate_database(root)


@dataclass(frozen=True)
class BackupService:
    paths: RuntimePaths
    database: Database

    def _digest(self) -> str:
        paths = [self.paths.database]
        for folder in (self.paths.workbooks, self.paths.reports):
            paths.extend(sorted(p for p in folder.rglob("*") if p.is_file()))
        return sha256(
            "\n".join(
                f"{p.relative_to(self.paths.root).as_posix()}:{sha256(p.read_bytes())}"
                for p in paths
            ).encode()
        )

    def create(self, kind: str = "Manual") -> BackupEntry:
        try:
            if kind not in ("Manual", "Pre-Restore"):
                raise ValueError("Invalid type")
            with TemporaryDirectory(dir=self.paths.temp) as temporary:
                root = Path(temporary)
                target_db = root / "data/analyzer.sqlite3"
                target_db.parent.mkdir()
                with self.database.connection() as source:
                    destination = sqlite3.connect(target_db)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                # Artifacts are immutable. Select only files referenced by the DB snapshot.
                files = {"data/analyzer.sqlite3": target_db.read_bytes()}
                with Database(target_db).connection() as snapshot:
                    for table in ("workbook_artifacts", "report_artifacts"):
                        for row in snapshot.execute(f"SELECT path FROM {table}"):
                            path = (self.paths.root / row[0]).resolve()
                            if not path.is_relative_to(self.paths.root):
                                raise ValueError("Invalid source path")
                            files[path.relative_to(self.paths.root).as_posix()] = path.read_bytes()
                timestamp = datetime.now(UTC).isoformat()
                manifest = {
                    "format": 1,
                    "application_version": APPLICATION_VERSION,
                    "timestamp": timestamp,
                    "kind": kind,
                    "files": {name: sha256(data) for name, data in files.items()},
                }
                stream = BytesIO()
                with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest))
                    for name, data in files.items():
                        archive.writestr(name, data)
                payload = stream.getvalue()
                _, checked = _validate(payload)
                _stage(checked, root)
                path = self.paths.backups / f"{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid4()}.irabackup"
                atomic_write(path, payload)
                return BackupEntry(
                    path, timestamp, kind, APPLICATION_VERSION, len(payload), "Verified"
                )
        except Exception:
            raise DomainError(
                ErrorCode.BACKUP_FAILED, "Backup failed; no complete backup was saved."
            ) from None

    def history(self) -> tuple[BackupEntry, ...]:
        entries: list[BackupEntry] = []
        for path in sorted(self.paths.backups.glob("*.irabackup"), reverse=True):
            try:
                payload = path.read_bytes()
                manifest, _ = _validate(payload)
                entries.append(
                    BackupEntry(
                        path,
                        manifest["timestamp"],
                        manifest["kind"],
                        manifest["application_version"],
                        len(payload),
                        "Verified",
                    )
                )
            except Exception:
                entries.append(
                    BackupEntry(
                        path, "Unavailable", "Unknown", "Unknown", path.stat().st_size, "Invalid"
                    )
                )
        return tuple(entries)

    def prepare_restore(self, source: Path) -> RestorePlan:
        try:
            payload = source.read_bytes()
            _, files = _validate(payload)
            with TemporaryDirectory(dir=self.paths.temp) as temporary:
                _stage(files, Path(temporary))
        except Exception:
            raise DomainError(
                ErrorCode.RESTORE_INVALID,
                "Restore rejected: incompatible, incomplete or damaged backup.",
            ) from None
        safety = self.create("Pre-Restore")
        return RestorePlan(payload, safety, self._digest())

    def restore(self, plan: RestorePlan, *, confirmed: bool) -> bool:
        if not confirmed:
            return False
        root = self.paths.root.resolve()
        stage = root.parent / f".{root.name}-restore-{uuid4()}"
        rollback = root.parent / f".{root.name}-rollback-{uuid4()}"
        journal = root.parent / f".{root.name}-restore.json"
        moved = False
        try:
            if self._digest() != plan.state_digest or not plan.safety.path.is_file():
                raise ValueError("State changed since confirmation was prepared")
            _, files = _validate(plan.payload)
            stage.mkdir()
            _stage(files, stage)
            RuntimePaths(stage).initialize()
            # Permanent backup history is a separate archive, never merged into analysis state.
            shutil.copytree(self.paths.backups, stage / "backups", dirs_exist_ok=True)
            atomic_write(
                journal, json.dumps({"restore": stage.name, "rollback": rollback.name}).encode()
            )
            replace_directory(root, rollback)
            moved = True
            replace_directory(stage, root)
            moved = False
        except Exception:
            if moved:
                replace_directory(rollback, root)
            raise DomainError(
                ErrorCode.RESTORE_INVALID, "Restore failed; the previous state was retained."
            ) from None
        finally:
            for directory in (stage, rollback):
                # Never remove the only surviving state after an unsuccessful rollback.
                if (
                    directory.exists()
                    and root.exists()
                    and directory.resolve().parent == root.parent
                ):
                    shutil.rmtree(directory)
            if root.exists():
                journal.unlink(missing_ok=True)
        return True
