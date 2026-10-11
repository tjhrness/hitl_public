"""Backup history and explicit replacement confirmation, through services only."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from inter_rater_analyzer.backups import RestorePlan
from inter_rater_analyzer.services import Services
from inter_rater_analyzer.wizard import TaskThread


class BackupPage(QWidget):
    restored = Signal()

    def __init__(self, services: Services, maintenance: Callable[[bool], bool]) -> None:
        super().__init__()
        self.services = services
        self.maintenance = maintenance
        self.worker: TaskThread | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Backups are permanent and unencrypted. Store this computer securely.")
        )
        self.history = QTextBrowser()
        layout.addWidget(self.history)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.create_button = QPushButton("Create manual backup")
        self.restore_button = QPushButton("Restore from file…")
        layout.addWidget(self.create_button)
        layout.addWidget(self.restore_button)
        self.create_button.clicked.connect(self.create_backup)
        self.restore_button.clicked.connect(self.choose_restore)
        self.refresh()

    def refresh(self) -> None:
        self.history.setPlainText(
            "\n\n".join(
                f"{e.timestamp} · {e.kind} · v{e.version} · {e.size:,} bytes · {e.integrity}"
                for e in self.services.backups.history()
            )
            or "No backups yet."
        )

    def run(self, operation: Callable[[], object], completed: Callable[[object], None]) -> None:
        if self.worker or not self.maintenance(True):
            self.message.setText("Wait for the current operation to finish.")
            return
        self.create_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.message.setText("Working on local backup storage…")
        self.worker = TaskThread(operation, self)

        def succeeded(result: object) -> None:
            self.finish(result, completed)

        def failed(message: str) -> None:
            self.finish(message, self.failed)

        self.worker.succeeded.connect(succeeded)
        self.worker.failed.connect(failed)
        self.worker.start()

    def finish(self, result: object, completed: Callable[[object], None]) -> None:
        assert self.worker is not None
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.maintenance(False)
        self.create_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.refresh()
        completed(result)

    def failed(self, message: object) -> None:
        self.message.setText(str(message))

    def create_backup(self) -> None:
        self.run(
            self.services.backups.create,
            lambda _: self.message.setText("Backup verified and saved."),
        )

    def choose_restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select backup", "", "IRA backup (*.irabackup)")
        if path:
            self.prepare_restore(Path(path))

    def prepare_restore(self, path: Path) -> None:
        self.run(lambda: self.services.backups.prepare_restore(path), self.confirm_restore)

    def confirm_restore(self, result: object) -> None:
        assert isinstance(result, RestorePlan)
        answer = QMessageBox.warning(
            self,
            "Replace all current analysis state?",
            "The selected backup has been verified and a permanent Pre-Restore safety backup "
            "has been saved. Restoring replaces all current analyses, drafts, presets and reports. "
            "Existing backup history is retained. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.message.setText("Restore cancelled. Current state retained; safety backup saved.")
            return
        self.run(
            lambda: self.services.backups.restore(result, confirmed=True), self.restore_complete
        )

    def restore_complete(self, _: object) -> None:
        self.message.setText("Restore complete. Saved state has been reloaded.")
        self.restored.emit()
