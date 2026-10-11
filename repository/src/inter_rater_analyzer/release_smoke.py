"""Explicit isolated acceptance run for a frozen application on an offline Windows machine."""

import json
from dataclasses import replace
from pathlib import Path

from openpyxl import Workbook
from PySide6.QtWidgets import QApplication, QLabel, QTextBrowser

from inter_rater_analyzer.app import create_application
from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.domain import RatingType, VersionType
from inter_rater_analyzer.privacy import check_artifact, check_text
from inter_rater_analyzer.results_ui import ResultsDashboard
from inter_rater_analyzer.services import Services


def run(root: Path) -> int:
    """Caller must choose a new empty scratch directory; existing state is never touched."""
    root = root.resolve()
    if root.exists():
        raise ValueError("Acceptance directory must not already exist")
    root.mkdir(parents=True)
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Review"
    sheet.append(["Item ID", "Rater:PrivateCanaryAlpha", "Rater:PrivateCanaryBeta"])
    for index, ratings in enumerate((("Yes", "No"), ("Yes", "Yes"), ("No", "No"), ("No", "Yes"))):
        sheet.append([f"I{index}", *ratings])
    source = root / "input.xlsx"
    book.save(source)
    book.close()
    services = Services.open(root / "state")
    services.drafts.create("Offline acceptance")
    services.drafts.attach_workbook(source)
    state = services.drafts.active()
    assert state is not None
    config = AnalysisConfiguration(
        (CriterionConfiguration("Review", RatingType.NOMINAL, metrics=("raw_agreement",)),)
    )
    state = replace(
        state,
        configuration=config,
        types_locked=True,
        acknowledged_warnings=("WARNING_SAMPLE_SIZE",),
    )
    services.drafts.save(state)
    services.execution.execute(state.version_id, worker_processes=True)
    latest = services.versions.create(
        state.version_id,
        VersionType.CONFIGURATION_ONLY,
        "Confidence 90 percent",
        configuration=replace(config, confidence=90),
    )
    services.drafts.save(replace(latest, acknowledged_warnings=("WARNING_SAMPLE_SIZE",)))
    services.execution.execute(latest.version_id, worker_processes=True)
    services.comparisons.latest(latest.version_id)
    report = services.reports.generate(latest.version_id)
    private = ("PrivateCanaryAlpha", "PrivateCanaryBeta")
    check_artifact(report.path.name, report.path.read_bytes(), private)
    check_text(json.dumps(services.execution.load(latest.version_id)), private)
    app, window = create_application([], root=services.paths.root)
    dashboard = ResultsDashboard(services, latest.version_id)
    dashboard.resize(1100, 760)
    dashboard.show()
    app.processEvents()
    for label in dashboard.findChildren(QLabel):
        check_text(label.text(), private)
    for browser in dashboard.findChildren(QTextBrowser):
        check_text(browser.toPlainText(), private)
    assert dashboard.tabs.count() == 6
    assert "I0" in dashboard.presenter.item_text("I0")
    dashboard.grab().save(str(root / "dashboard.png"))
    dashboard.close()
    window.close()
    backup = services.backups.create()
    services.drafts.create("State that restore replaces")
    plan = services.backups.prepare_restore(backup.path)
    services.backups.restore(plan, confirmed=True)
    restarted = Services.open(services.paths.root)
    assert restarted.drafts.active() is None
    assert restarted.execution.load(latest.version_id)
    record = {
        "passed": True,
        "checks": [
            "analysis in worker process",
            "version",
            "comparison",
            "results UI",
            "drill down",
            "report privacy",
            "backup",
            "restore",
            "restart",
        ],
        "network_isolation": "Must be supplied by the acceptance host or Windows Sandbox",
    }
    (root / "acceptance.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    QApplication.processEvents()
    return 0
