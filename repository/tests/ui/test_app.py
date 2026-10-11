import socket


def test_construct_without_network_or_showing(qtbot, monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    from inter_rater_analyzer.app import create_application

    app, window = create_application([], root=tmp_path)
    qtbot.addWidget(window)
    assert app is not None
    assert window.windowTitle() == "Inter-Rater Variability Analyzer"
    assert not window.isVisible()
