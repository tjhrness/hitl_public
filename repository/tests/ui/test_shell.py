import pytest

from inter_rater_analyzer.app import create_application
from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.services import Services


def test_navigation_draft_and_history(qtbot, tmp_path):
    services = Services.open(tmp_path)
    services.drafts.create("Pilot")
    _, window = create_application([], root=tmp_path)
    qtbot.addWidget(window)
    assert [window.navigation.item(i).text() for i in range(5)] == [
        "New Analysis",
        "Analysis History",
        "Presets",
        "Backup History",
        "Settings",
    ]
    assert "Resume Draft" in window.pages.widget(0).toPlainText()
    for index in range(5):
        window.navigation.setCurrentRow(index)
        assert window.pages.currentIndex() == index
    window.navigation.setCurrentRow(1)
    assert "Pilot" in window.pages.currentWidget().toPlainText()


def test_startup_error_is_safe(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("private source identity")

    monkeypatch.setattr(Services, "open", fail)
    with pytest.raises(DomainError) as captured:
        create_application([], root=tmp_path)
    assert "private" not in str(captured.value)
