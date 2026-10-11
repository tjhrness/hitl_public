import hashlib
import os

import pytest

from inter_rater_analyzer.artifacts import atomic_write, sanitize_filename
from inter_rater_analyzer.domain import DomainError, VersionStatus
from inter_rater_analyzer.services import Services


@pytest.mark.parametrize("name", ["CON", "NUL.txt", "COM1.xlsx", "../bad:<>name. ", ""])
def test_windows_sanitization(name):
    safe = sanitize_filename(name)
    assert safe and not any(character in safe for character in "/\\:<>")
    assert safe.split(".")[0].upper() not in {"CON", "NUL", "COM1"}
    assert safe == safe.rstrip(". ")


def test_workbook_copy_survives_source_deletion(tmp_path):
    services = Services.open(tmp_path / "app")
    _, version = services.analyses.create("Study")
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"original bytes")
    artifact = services.artifacts.import_workbook(version.id, source)
    source.unlink()
    assert artifact.sha256 == hashlib.sha256(b"original bytes").hexdigest()
    assert services.artifacts.verify(artifact)
    assert services.artifacts.get(artifact.id) == artifact
    services.analyses.finish(version.id, VersionStatus.ABANDONED)
    with pytest.raises(DomainError):
        services.artifacts.import_workbook(version.id, tmp_path / "missing.xlsx")


def test_atomic_cleanup(tmp_path, monkeypatch):
    target = tmp_path / "artifact"

    def fail(*args, **kwargs):
        raise OSError("injected")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write(target, b"abc")
    assert list(tmp_path.iterdir()) == []
