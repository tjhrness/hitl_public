import json
import sqlite3
from dataclasses import replace

import pytest
from openpyxl import load_workbook

from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType, VersionStatus, VersionType
from inter_rater_analyzer.services import Services
from tests.workbook_fixtures.builders import workbook


def prepared(tmp_path, metrics=("raw_agreement",), additional_rows=()):
    services = Services.open(tmp_path / "state")
    services.drafts.create("Study")
    source = workbook(tmp_path / "source.xlsx")
    book = load_workbook(source)
    for row in additional_rows:
        book.active.append(row)
    book.save(source)
    book.close()
    services.drafts.attach_workbook(source)
    state = replace(
        services.drafts.active(),
        types_locked=True,
        configuration=AnalysisConfiguration(
            (CriterionConfiguration("Criterion 0", RatingType.NOMINAL, metrics=metrics),)
        ),
        acknowledged_warnings=("WARNING_SAMPLE_SIZE",),
    )
    services.drafts.save(state)
    return services, state


def test_complete_snapshot_restart_and_immutability(tmp_path):
    services, state = prepared(tmp_path)
    result = services.execution.execute(state.version_id)
    assert services.analyses.get_version(state.version_id).status is VersionStatus.COMPLETED
    saved = Services.open(tmp_path / "state").execution.load(state.version_id)
    assert saved["result"]["ranking"][0]["item_id"] == result.ranking[0].item_id
    assert "Alice" not in json.dumps(saved) and "Bob" not in json.dumps(saved)
    with pytest.raises(DomainError):
        services.execution.execute(state.version_id)
    with services.database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE execution_results SET payload=?", ("{}",))


def test_preflight_does_not_start_or_fail_draft(tmp_path):
    services, state = prepared(tmp_path, ("cohen_kappa",))
    with pytest.raises(DomainError):
        services.execution.execute(state.version_id)
    assert services.analyses.get_version(state.version_id).status is VersionStatus.DRAFT
    with services.database.connection() as conn:
        assert conn.execute("SELECT count(*) FROM execution_snapshots").fetchone()[0] == 0


def test_midrun_failure_rolls_back_and_records_safe_history(tmp_path, monkeypatch):
    services, state = prepared(tmp_path)

    def fail(*args, **kwargs):
        with pytest.raises(sqlite3.IntegrityError):
            services.drafts.save(state)
        raise RuntimeError("secret original rater identity")

    monkeypatch.setattr("inter_rater_analyzer.execution.analyze_workbook", fail)
    with pytest.raises(DomainError, match="failed"):
        services.execution.execute(state.version_id)
    assert services.analyses.get_version(state.version_id).status is VersionStatus.FAILED
    with services.database.connection() as conn:
        assert conn.execute("SELECT count(*) FROM execution_results").fetchone()[0] == 0
        payload = conn.execute("SELECT payload FROM execution_failures").fetchone()[0]
        assert "secret" not in payload
        assert "RuntimeError" in payload


def test_completed_requires_real_results(tmp_path):
    services, state = prepared(tmp_path)
    with pytest.raises(DomainError):
        services.analyses.finish(state.version_id, VersionStatus.COMPLETED)


def test_interrupted_execution_recovered_as_failed(tmp_path):
    from inter_rater_analyzer.drafts import encode

    services, state = prepared(tmp_path)
    with services.database.connection() as conn:
        conn.execute(
            "INSERT INTO execution_snapshots VALUES(?,?)", (str(state.version_id), encode(state))
        )
    services.execution.recover_interrupted()
    assert services.analyses.get_version(state.version_id).status is VersionStatus.FAILED
    assert services.drafts.active() is None
    services.execution.recover_interrupted()


def test_nominal_raw_agreement_cannot_be_omitted(tmp_path):
    services, state = prepared(tmp_path, metrics=())
    with pytest.raises(DomainError, match="raw percentage"):
        services.execution.execute(state.version_id)
    assert services.analyses.get_version(state.version_id).status is VersionStatus.DRAFT


def test_persistence_failure_rolls_back_inserted_result(tmp_path):
    services, state = prepared(tmp_path)
    with services.database.connection() as conn:
        conn.execute(
            "CREATE TRIGGER injected_failure BEFORE UPDATE ON analysis_versions "
            "WHEN NEW.status='Completed' BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(DomainError):
        services.execution.execute(state.version_id)
    assert services.analyses.get_version(state.version_id).status is VersionStatus.FAILED
    with services.database.connection() as conn:
        assert conn.execute("SELECT count(*) FROM execution_results").fetchone()[0] == 0


def test_identical_input_new_version_has_identical_results(tmp_path):
    services, state = prepared(tmp_path)
    first = services.execution.execute(state.version_id)
    previous = services.analyses.get_version(state.version_id)
    version = services.analyses.new_version(
        previous.analysis_id, VersionType.CONFIGURATION_ONLY, "Reproduce"
    )
    services.drafts.attach_workbook(tmp_path / "source.xlsx")
    services.drafts.save(
        replace(
            services.drafts.active(),
            configuration=state.configuration,
            types_locked=True,
            acknowledged_warnings=state.acknowledged_warnings,
        )
    )
    assert services.execution.execute(version.id) == first
    assert (
        services.execution.load(version.id)["seed_key"]
        == services.execution.load(state.version_id)["seed_key"]
    )
