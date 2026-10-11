from dataclasses import replace

import pytest
from openpyxl import load_workbook

from inter_rater_analyzer.domain import DomainError, VersionType
from tests.integration.test_execution import prepared


def test_latest_previous_cells_consensus_priority_and_metric_intersection(tmp_path):
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    source = tmp_path / "source.xlsx"
    book = load_workbook(source)
    book.active["B2"] = "No"
    book.save(source)
    book.close()
    new = services.versions.create(
        state.version_id, VersionType.DATA_CHANGE, "Agree", source=source
    )
    services.drafts.save(
        replace(new, acknowledged_warnings=("WARNING_SAMPLE_SIZE", "WARNING_SEVERE_IMBALANCE"))
    )
    services.execution.execute(new.version_id)
    result = services.comparisons.latest(new.version_id)
    assert len(result.cells) == 1
    assert result.cells[0].alias == "Rater A"
    assert result.cells[0].magnitude == 1
    assert result.consensus[0].previous is None
    assert result.consensus[0].latest == "no"
    assert result.priorities[0].change < 0
    assert result.metrics[0].latest["estimate"] == 100
    with pytest.raises(DomainError):
        services.comparisons.latest(state.version_id)


def test_config_difference_and_previous_zero_na(tmp_path):
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    config = replace(state.configuration, confidence=90)
    new = services.versions.create(
        state.version_id, VersionType.CONFIGURATION_ONLY, "Confidence", configuration=config
    )
    services.drafts.save(replace(new, acknowledged_warnings=state.acknowledged_warnings))
    services.execution.execute(new.version_id)
    result = services.comparisons.latest(new.version_id)
    assert result.configuration_changes == (("confidence", 95.0, 90),)
    assert result.cells == ()
    assert result.priorities[0].change == 0
