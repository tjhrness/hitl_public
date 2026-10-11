import sqlite3

import pytest

from inter_rater_analyzer.database import Database, Migration, transaction


def test_reinitialize_and_foreign_keys(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    db.initialize()
    with db.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        assert conn.execute("SELECT schema_version FROM app_metadata").fetchone()[0] == 1
        conn.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child(parent_id INTEGER REFERENCES parent(id))")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO child VALUES(1)")


def test_migration_order_and_failed_rollback(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    with pytest.raises(sqlite3.OperationalError):
        db.initialize((Migration(2, ("CREATE TABLE temporary_table(x)", "INVALID SQL")),))
    with db.connection() as conn:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='temporary_table'").fetchone()
            is None
        )
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 1
    db.initialize(
        (
            Migration(3, ("INSERT INTO example VALUES (7)",)),
            Migration(2, ("CREATE TABLE example(x)",)),
        )
    )
    with db.connection() as conn:
        assert conn.execute("SELECT x FROM example").fetchone()[0] == 7


def test_transactions(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    with db.connection() as conn:
        conn.execute("CREATE TABLE example(x)")
        with transaction(conn):
            conn.execute("INSERT INTO example VALUES(1)")
        with pytest.raises(ValueError), transaction(conn):
            conn.execute("INSERT INTO example VALUES(2)")
            raise ValueError("injected")
        assert [row[0] for row in conn.execute("SELECT x FROM example")] == [1]
