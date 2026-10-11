from inter_rater_analyzer.domain import VersionStatus
from inter_rater_analyzer.services import Services
from inter_rater_analyzer.wizard import AnalysisWizard
from tests.workbook_fixtures.builders import workbook


def setup(qtbot, tmp_path):
    services = Services.open(tmp_path / "state")
    wizard = AnalysisWizard(services)
    qtbot.addWidget(wizard)
    wizard.name.setText("UI study")
    wizard.start_draft()
    with qtbot.waitSignal(wizard.task_done, timeout=10000):
        wizard.import_path(workbook(tmp_path / "input.xlsx"))
    wizard.confirm_types()
    return services, wizard


def test_real_workflow_and_progress(qtbot, tmp_path):
    services, wizard = setup(qtbot, tmp_path)
    assert wizard.preview_tables[0].rowCount() == 1
    assert wizard.preview_tables[0].horizontalHeaderItem(1).text() == "Rater A"
    assert services.drafts.active().types_locked
    for key, check in wizard.metric_checks["Criterion 0"].items():
        check.setChecked(key == "raw_agreement")
    wizard.prepare_review()
    wizard.acknowledge.setChecked(True)
    wizard.prepare_review()
    assert wizard.review.isReadOnly()
    identifier = services.drafts.active().version_id
    with qtbot.waitSignal(wizard.task_done, timeout=15000):
        wizard.execute()
    assert services.analyses.get_version(identifier).status is VersionStatus.COMPLETED
    assert wizard.progress.text() == "Completed"
    assert wizard.start_button.isEnabled()


def test_preflight_returns_to_configuration_and_resumes(qtbot, tmp_path):
    services, wizard = setup(qtbot, tmp_path)
    for key, check in wizard.metric_checks["Criterion 0"].items():
        check.setChecked(key == "cohen_kappa")
    wizard.prepare_review()
    wizard.acknowledge.setChecked(True)
    wizard.prepare_review()
    with qtbot.waitSignal(wizard.task_done, timeout=15000):
        wizard.execute()
    assert services.drafts.active() is not None
    assert wizard.tabs.currentIndex() == 2
    resumed = AnalysisWizard(services)
    qtbot.addWidget(resumed)
    assert resumed.type_boxes["Criterion 0"].isEnabled() is False
