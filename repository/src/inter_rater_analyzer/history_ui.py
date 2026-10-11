"""History actions and permanent preset creation through application services."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from inter_rater_analyzer.domain import AnalysisVersionId, DomainError, VersionType
from inter_rater_analyzer.results_ui import ResultsDashboard
from inter_rater_analyzer.services import Services
from inter_rater_analyzer.wizard import TaskThread


class HistoryPage(QWidget):
    draft_created = Signal()

    def __init__(self, services: Services) -> None:
        super().__init__()
        self.services = services
        self.layout_box = QVBoxLayout(self)
        self.selector = QComboBox()
        self.layout_box.addWidget(self.selector)
        actions = QHBoxLayout()
        for label, operation in (
            ("Open results", self.open_results),
            ("New version", self.new_version),
            ("Save as permanent preset", self.save_preset),
            ("Generate report ZIP", self.generate_report),
        ):
            button = QPushButton(label)
            button.clicked.connect(operation)
            actions.addWidget(button)
        self.layout_box.addLayout(actions)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.layout_box.addWidget(self.message)
        self.dashboard: ResultsDashboard | None = None
        self.worker: TaskThread | None = None
        self.refresh()

    def refresh(self) -> None:
        self.selector.clear()
        for entry in self.services.history.list():
            self.selector.addItem(
                f"{entry.name} · v{entry.number} · {entry.status}", str(entry.version_id)
            )
        if not self.selector.count():
            self.message.setText("No analyses yet.")

    def toPlainText(self) -> str:
        return "\n".join(self.selector.itemText(i) for i in range(self.selector.count()))

    def selected(self) -> AnalysisVersionId | None:
        value = self.selector.currentData()
        return AnalysisVersionId.parse(value) if value else None

    def open_results(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        try:
            dashboard = ResultsDashboard(self.services, identifier)
        except DomainError as error:
            self.message.setText(error.message)
            return
        if self.dashboard:
            self.layout_box.removeWidget(self.dashboard)
            self.dashboard.deleteLater()
        self.dashboard = dashboard
        self.layout_box.addWidget(dashboard, 1)
        self.message.clear()

    def new_version(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        kind, ok = QInputDialog.getItem(
            self, "New version", "Version type", [k.value for k in VersionType], 0, False
        )
        if not ok:
            return
        note, ok = QInputDialog.getText(self, "New version", "Required change note")
        if not ok:
            return
        source: Path | None = None
        if VersionType(kind) is VersionType.DATA_CHANGE:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Replacement workbook", "", "Excel (*.xlsx)"
            )
            if not filename:
                return
            source = Path(filename)
        try:
            self.services.versions.create(identifier, VersionType(kind), note, source=source)
            self.refresh()
            self.draft_created.emit()
        except DomainError as error:
            self.message.setText(error.message)

    def save_preset(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        name, ok = QInputDialog.getText(self, "Permanent preset", "New preset name")
        if not ok:
            return
        fraction, ok = QInputDialog.getDouble(
            self,
            "Tolerance rule",
            "Fraction of observed range for future continuous criteria",
            0.05,
            0,
            100,
            6,
        )
        if not ok:
            return
        try:
            self.services.presets.create_from_version(name, identifier, tolerance_fraction=fraction)
            self.message.setText("Permanent preset saved.")
        except DomainError as error:
            self.message.setText(error.message)

    def generate_report(self) -> None:
        identifier = self.selected()
        if identifier is None or (self.worker and self.worker.isRunning()):
            return
        self.message.setText("Generating report package")
        self.worker = TaskThread(lambda: self.services.reports.generate(identifier), self)
        self.worker.succeeded.connect(self.report_saved)
        self.worker.failed.connect(self.message.setText)
        self.worker.start()

    def report_saved(self, artifact: object) -> None:
        from inter_rater_analyzer.reports import ReportArtifact

        if isinstance(artifact, ReportArtifact):
            self.message.setText(f"Report saved: {artifact.path}")
