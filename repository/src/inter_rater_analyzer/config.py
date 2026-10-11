"""Offline runtime configuration and the single filesystem layout authority."""

import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryFile
from typing import Final

from inter_rater_analyzer.domain import DomainError, ErrorCode

APPLICATION_VERSION: Final = "0.1.0"
BOOTSTRAP_RESAMPLES: Final = 10_000
MASTER_SEED: Final = 1729


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    def __post_init__(self) -> None:
        root = self.root.resolve()
        value = str(root)
        if os.name == "nt" and not value.startswith("\\\\?\\"):
            # Explicit extended paths work even when Windows LongPathsEnabled is off.
            value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
            root = Path(value)
        object.__setattr__(self, "root", root)

    @classmethod
    def resolve(cls, override: Path | None = None) -> RuntimePaths:
        if override is not None:
            return cls(override.resolve())
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise DomainError(ErrorCode.SYSTEM_PATH, "Set LOCALAPPDATA before starting the app.")
        return cls(Path(local).resolve() / "InterRaterAnalyzer")

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def database(self) -> Path:
        return self.data / "analyzer.sqlite3"

    @property
    def workbooks(self) -> Path:
        return self.root / "workbooks"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def directories(self) -> tuple[Path, ...]:
        return self.data, self.workbooks, self.reports, self.backups, self.logs, self.temp

    def initialize(self) -> None:
        try:
            for directory in self.directories:
                directory.mkdir(parents=True, exist_ok=True)
                with TemporaryFile(dir=directory) as probe:
                    probe.write(b"writability check")
                    probe.flush()
                    os.fsync(probe.fileno())
        except OSError as error:
            raise DomainError(
                ErrorCode.SYSTEM_PATH,
                "Cannot initialize application storage. Check permissions and disk space.",
            ) from error
