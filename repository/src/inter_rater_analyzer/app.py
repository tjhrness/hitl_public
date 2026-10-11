"""Desktop entry point; constructing the shell does not show it."""

import os
import sys
from multiprocessing import freeze_support
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QCloseEvent, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTextBrowser,
    QWidget,
)

from inter_rater_analyzer.backup_ui import BackupPage
from inter_rater_analyzer.config import RuntimePaths
from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.history_ui import HistoryPage
from inter_rater_analyzer.presenter import NAVIGATION, ShellPresenter
from inter_rater_analyzer.services import Services
from inter_rater_analyzer.wizard import AnalysisWizard

THEME = """
QWidget {font-family: 'Segoe UI'; font-size: 10pt; color: #182b40; background: #f4f6fa;}
QListWidget {background: #142b43; color: #f4f8ff; border: none; padding: 12px;}
QListWidget::item {padding: 14px 8px; border-radius: 5px;}
QListWidget::item:selected {background: #286d91; color: white;}
QTextBrowser {background: white; border: 1px solid #d5deea; padding: 24px; font-size: 11pt;}
QPushButton {background: #176b88; color: white; border: none;
padding: 9px 18px; border-radius: 4px;}
QPushButton:disabled {background: #9ba9b5;}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {background: white; padding: 5px;}
QTableView {background: white; alternate-background-color: #edf3f8; gridline-color: #d5deea;}
"""


class MainWindow(QMainWindow):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self.services = services
        self.presenter = ShellPresenter(services)
        self.navigation = QListWidget()
        self.navigation.addItems(list(NAVIGATION))
        self.navigation.setFixedWidth(220)
        self.pages = QStackedWidget()
        self.wizard = AnalysisWizard(services)
        self.wizard.completed.connect(self.show_completed)
        self.pages.addWidget(self.wizard)
        self.history_page = HistoryPage(services)
        self.history_page.draft_created.connect(self.resume_draft)
        self.pages.addWidget(self.history_page)
        for index in range(2, len(NAVIGATION)):
            if index == 3:
                self.backup_page = BackupPage(services, self.maintenance)
                self.backup_page.restored.connect(self.reload_state)
                self.pages.addWidget(self.backup_page)
                continue
            page = QTextBrowser()
            page.setPlainText(self.presenter.page(index))
            self.pages.addWidget(page)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 16, 16)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(THEME)
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("Offline · All data stays on this computer")

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            (self.wizard.worker and self.wizard.worker.isRunning())
            or (self.history_page.worker and self.history_page.worker.isRunning())
            or (self.backup_page.worker and self.backup_page.worker.isRunning())
        ):
            self.statusBar().showMessage("Wait for the current operation to finish before closing.")
            event.ignore()
        else:
            self.wizard.timer.stop()
            self.wizard.autosave()
            event.accept()

    def navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        page = self.pages.widget(index)
        if isinstance(page, QTextBrowser):
            page.setPlainText(self.presenter.page(index))
        if index == 1:
            self.history_page.refresh()
        if index == 3:
            self.backup_page.refresh()

    def maintenance(self, active: bool) -> bool:
        if active and any(
            worker and worker.isRunning()
            for worker in (self.wizard.worker, self.history_page.worker)
        ):
            return False
        if active:
            pending_save = self.wizard.timer.isActive()
            self.wizard.timer.stop()
            if pending_save:
                self.wizard.autosave()
        self.navigation.setEnabled(not active)
        self.wizard.setEnabled(not active)
        self.history_page.setEnabled(not active)
        return True

    def reload_state(self) -> None:
        self.services.execution.recover_interrupted()
        self.wizard.timer.stop()
        self.resume_draft()
        self.pages.removeWidget(self.history_page)
        self.history_page.deleteLater()
        self.history_page = HistoryPage(self.services)
        self.history_page.draft_created.connect(self.resume_draft)
        self.pages.insertWidget(1, self.history_page)
        self.navigation.setCurrentRow(3)

    def show_completed(self, _: object) -> None:
        self.navigation.setCurrentRow(1)
        self.history_page.refresh()
        self.history_page.open_results()

    def resume_draft(self) -> None:
        self.pages.removeWidget(self.wizard)
        self.wizard.deleteLater()
        self.wizard = AnalysisWizard(self.services)
        self.wizard.completed.connect(self.show_completed)
        self.pages.insertWidget(0, self.wizard)
        self.navigation.setCurrentRow(0)


def create_application(
    argv: list[str] | None = None, *, root: Path | None = None
) -> tuple[QApplication, MainWindow]:
    try:
        services = Services.open(root)
    except Exception:
        raise DomainError(
            ErrorCode.SYSTEM_PATH,
            "Application could not open local storage. Check access and free space.",
        ) from None
    existing = QApplication.instance()
    if existing is not None and not isinstance(existing, QApplication):
        raise RuntimeError("A non-GUI Qt application is already running.")
    app = existing if isinstance(existing, QApplication) else QApplication(argv or [])
    if "Segoe UI" not in QFontDatabase.families():
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setApplicationName("Inter-Rater Variability Analyzer")
    window = MainWindow(services)
    window.setWindowTitle(app.applicationName())
    window.resize(1100, 760)
    return app, window


def main() -> int:
    freeze_support()
    runtime = RuntimePaths.resolve()
    runtime.root.parent.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(runtime.root.parent / ".InterRaterAnalyzer.instance.lock"))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        existing = QApplication.instance()
        app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
        QMessageBox.information(
            None, "Application already running", "Use the existing analyzer window."
        )
        return 1
    try:
        Services.open(runtime.root).execution.recover_interrupted()
        app, window = create_application(sys.argv)
    except DomainError as error:
        existing = QApplication.instance()
        app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
        QMessageBox.critical(None, "Startup failed", error.message)
        return 1
    window.show()
    return app.exec()
