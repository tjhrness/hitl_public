from dataclasses import replace

from inter_rater_analyzer.domain import VersionType
from inter_rater_analyzer.results_ui import ReadOnlyModel, ResultsDashboard
from tests.integration.test_execution import prepared


def test_conditional_comparison_and_virtualized_rows(qtbot, tmp_path):
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    new = services.versions.create(state.version_id, VersionType.CONFIGURATION_ONLY, "Repeat")
    services.drafts.save(replace(new, acknowledged_warnings=state.acknowledged_warnings))
    services.execution.execute(new.version_id)
    dashboard = ResultsDashboard(services, new.version_id)
    qtbot.addWidget(dashboard)
    assert dashboard.tabs.tabText(5) == "Version Comparison"
    model = ReadOnlyModel(("Item",), tuple((str(i),) for i in range(1000)))
    assert model.rowCount() == 1000
    assert model.data(model.index(999, 0)) == "999"


def test_persisted_dashboard_order_drilldown_and_privacy(qtbot, tmp_path):
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    dashboard = ResultsDashboard(services, state.version_id)
    qtbot.addWidget(dashboard)
    assert [dashboard.tabs.tabText(i) for i in range(dashboard.tabs.count())] == [
        "Executive Summary",
        "Cross-Criteria Comparison",
        "Criterion Details",
        "Rater Diagnostics",
        "Human-Review Priority List",
    ]
    assert dashboard.ranking.model().rowCount() == 1
    dashboard.show_item("Q1")
    text = dashboard.detail.toPlainText()
    assert "Rater A" in text and "No consensus" in text
    assert "contribution" in text.lower()
    assert "Alice" not in text and "Bob" not in text
    assert "What does this mean?" in dashboard.help_button.text()
