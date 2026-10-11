from PySide6.QtWidgets import QMessageBox

from inter_rater_analyzer.app import create_application


def test_backup_and_restore_confirmation(qtbot, tmp_path, monkeypatch):
    _, window = create_application([], root=tmp_path / "state")
    qtbot.addWidget(window)
    page = window.backup_page
    window.navigation.setCurrentRow(3)
    page.create_backup()
    qtbot.waitUntil(lambda: page.worker is None)
    assert "Manual" in page.history.toPlainText()
    source = window.services.backups.history()[0].path
    window.services.drafts.create("Replace me")
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.No)
    page.prepare_restore(source)
    qtbot.waitUntil(lambda: "cancelled" in page.message.text())
    assert window.services.drafts.active() is not None
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Yes)
    page.prepare_restore(source)
    qtbot.waitUntil(lambda: "Restore complete" in page.message.text())
    assert window.services.drafts.active() is None
    assert "Pre-Restore" in page.history.toPlainText()
    assert window.navigation.isEnabled()
