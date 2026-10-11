from pathlib import Path

import pytest

from inter_rater_analyzer.config import BOOTSTRAP_RESAMPLES, MASTER_SEED, RuntimePaths
from inter_rater_analyzer.domain import DomainError, ErrorCode


def test_paths_override_and_production_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "profile"))
    production = RuntimePaths.resolve()
    production.initialize()
    assert production.root.samefile(tmp_path / "profile" / "InterRaterAnalyzer")
    paths = RuntimePaths.resolve(tmp_path / "test")
    paths.initialize()
    paths.initialize()
    for directory in paths.directories:
        assert directory.is_dir()
        assert directory.parent == paths.root
    assert (BOOTSTRAP_RESAMPLES, MASTER_SEED) == (10000, 1729)


def test_missing_environment(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(DomainError, match="LOCALAPPDATA"):
        RuntimePaths.resolve()


def test_unwritable_root(tmp_path, monkeypatch):
    paths = RuntimePaths.resolve(tmp_path)

    def denied(*args, **kwargs):
        raise PermissionError("private filesystem details")

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(DomainError) as error:
        paths.initialize()
    assert error.value.code is ErrorCode.SYSTEM_PATH
    assert "private" not in str(error.value)
