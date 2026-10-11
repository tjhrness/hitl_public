import json
import socket

import pytest

from inter_rater_analyzer.privacy import check_artifact, check_text
from inter_rater_analyzer.services import Services
from tests.integration.test_execution import prepared


def test_end_to_end_without_network_and_public_privacy(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Runtime attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    services, state = prepared(tmp_path)
    services.execution.execute(state.version_id)
    check_text(json.dumps(services.execution.load(state.version_id)), ("Alice", "Bob"))
    report = services.reports.generate(state.version_id)
    check_artifact(report.path.name, report.path.read_bytes(), ("Alice", "Bob"))
    for log in services.paths.logs.rglob("*"):
        if log.is_file():
            check_artifact(log.name, log.read_bytes(), ("Alice", "Bob"))
    backup = services.backups.create()
    plan = services.backups.prepare_restore(backup.path)
    services.backups.restore(plan, confirmed=True)
    assert Services.open(services.paths.root).execution.load(state.version_id)


def test_scanner_rejects_text_and_nested_docx_leaks():
    from io import BytesIO
    from zipfile import ZipFile

    with pytest.raises(ValueError):
        check_text("Responsible: ALICE", ("Alice",))
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("word/document.xml", "<document><run>Ali</run><run>ce</run></document>")
    with pytest.raises(ValueError):
        check_artifact("report.docx", data.getvalue(), ("Alice",))
