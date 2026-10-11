import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.services import Services
from tests.integration.test_execution import prepared


def test_full_restore_safety_and_cancellation(tmp_path):
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    services.presets.create_from_version("Reusable", state.version_id)
    report = services.reports.generate(state.version_id)
    saved = services.execution.load(state.version_id)
    backup = services.backups.create()
    services.drafts.create("After backup")
    plan = services.backups.prepare_restore(backup.path)
    assert len(services.backups.history()) == 2
    assert plan.safety.kind == "Pre-Restore"
    assert not services.backups.restore(plan, confirmed=False)
    assert services.drafts.active() is not None
    assert services.backups.restore(plan, confirmed=True)
    restored = Services.open(services.paths.root)
    assert restored.drafts.active() is None
    assert restored.execution.load(state.version_id) == saved
    assert len(restored.presets.list()) == 1
    assert report.path.is_file()
    assert restored.artifacts.verify(restored.artifacts.get(state.workbook_id))
    assert len(restored.backups.history()) == 2


@pytest.mark.parametrize(
    "damage", ["corrupt", "manifest", "missing", "checksum", "version", "traversal"]
)
def test_invalid_backup_leaves_active_state_untouched(tmp_path, damage):
    services, _ = prepared(tmp_path)
    backup = services.backups.create()
    with ZipFile(backup.path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if damage == "manifest":
        del files["manifest.json"]
    elif damage == "missing":
        del files["data/analyzer.sqlite3"]
    elif damage == "checksum":
        files["data/analyzer.sqlite3"] += b"changed"
    elif damage == "version":
        manifest = json.loads(files["manifest.json"])
        manifest["application_version"] = "0.0.0"
        files["manifest.json"] = json.dumps(manifest).encode()
    elif damage == "traversal":
        files["../outside"] = b"bad"
    invalid = tmp_path / "invalid.irabackup"
    with ZipFile(invalid, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    if damage == "corrupt":
        invalid.write_bytes(b"invalid")
    before = services.paths.database.read_bytes()
    with pytest.raises(DomainError):
        services.backups.prepare_restore(invalid)
    assert services.paths.database.read_bytes() == before
    assert len(services.backups.history()) == 1


def test_staged_replace_failure_rolls_back(tmp_path, monkeypatch):
    services, _ = prepared(tmp_path)
    backup = services.backups.create()
    plan = services.backups.prepare_restore(backup.path)
    before = services.paths.database.read_bytes()
    from inter_rater_analyzer import backups

    original = backups.replace_directory
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Injected rename failure")
        original(source, target)

    monkeypatch.setattr(backups, "replace_directory", fail_second)
    with pytest.raises(DomainError):
        services.backups.restore(plan, confirmed=True)
    assert services.paths.database.read_bytes() == before
    assert services.drafts.active() is not None
    assert len(services.backups.history()) == 2


def test_restart_recovers_interrupted_swap(tmp_path):
    services, state = prepared(tmp_path)
    root = services.paths.root
    rollback = root.parent / f".{root.name}-rollback-interrupted"
    stage = root.parent / f".{root.name}-restore-interrupted"
    stage.mkdir()
    journal = root.parent / f".{root.name}-restore.json"
    journal.write_text(json.dumps({"restore": stage.name, "rollback": rollback.name}))
    root.rename(rollback)
    restarted = Services.open(root)
    assert restarted.drafts.active().version_id == state.version_id
    assert not journal.exists() and not stage.exists() and not rollback.exists()


def test_modified_state_rejects_stale_restore_plan(tmp_path):
    services = Services.open(tmp_path / "state")
    backup = services.backups.create()
    plan = services.backups.prepare_restore(backup.path)
    services.drafts.create("New work")
    with pytest.raises(DomainError):
        services.backups.restore(plan, confirmed=True)
    assert services.drafts.active() is not None


def test_restore_in_long_storage_path(tmp_path):
    import shutil

    # Keep active report paths valid while the longer sibling staging path exceeds MAX_PATH.
    base = tmp_path / ("long-profile-" + "x" * 42)
    base.mkdir()
    services, state = prepared(base)
    try:
        services.execution.execute(state.version_id)
        report = services.reports.generate(state.version_id)
        backup = services.backups.create()
        plan = services.backups.prepare_restore(backup.path)
        assert services.backups.restore(plan, confirmed=True)
        assert report.path.exists()
    finally:
        # Use the service's native path representation for deep Windows cleanup too.
        shutil.rmtree(services.paths.root)
