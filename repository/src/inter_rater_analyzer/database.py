"""SQLite connections and atomic, ordered schema migration."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from inter_rater_analyzer.config import APPLICATION_VERSION


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        1,
        (
            "CREATE TABLE app_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
            "schema_version INTEGER NOT NULL, application_version TEXT NOT NULL)",
        ),
    ),
)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[None]:
    if connection.in_transaction:
        raise RuntimeError("Nested transactions are not supported.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


@dataclass(frozen=True)
class Database:
    path: Path

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self, extra: tuple[Migration, ...] = ()) -> None:
        migrations = sorted((*MIGRATIONS, *extra), key=lambda migration: migration.version)
        versions = [migration.version for migration in migrations]
        if len(versions) != len(set(versions)) or any(number < 1 for number in versions):
            raise ValueError("Migration versions must be unique positive integers.")
        with self.connection() as connection, transaction(connection):
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            applied = {
                int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in migrations:
                if migration.version in applied:
                    continue
                if applied and migration.version < max(applied):
                    raise ValueError("Cannot insert a migration before an applied version.")
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES(?)", (migration.version,)
                )
                applied.add(migration.version)
            connection.execute(
                "INSERT INTO app_metadata VALUES(1, ?, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET schema_version=excluded.schema_version",
                (max(applied), APPLICATION_VERSION),
            )
