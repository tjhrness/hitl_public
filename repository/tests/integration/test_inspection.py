from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import load_workbook

from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.ingestion import inspect_workbook
from tests.workbook_fixtures.builders import workbook


@pytest.mark.parametrize("count", [1, 10])
def test_visible_counts(tmp_path, count):
    path = workbook(tmp_path / "input.xlsx", count)
    assert len(inspect_workbook(path).worksheets) == count


def test_hidden_and_case_sensitive_names(tmp_path):
    path = workbook(tmp_path / "input.xlsx", 3)
    book = load_workbook(path)
    book.worksheets[2].sheet_state = "hidden"
    book.save(path)
    book.close()
    with ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["xl/workbook.xml"] = members["xl/workbook.xml"].replace(b"Criterion 1", b"criterion 0")
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    assert [s.name for s in inspect_workbook(path).worksheets] == ["Criterion 0", "criterion 0"]


@pytest.mark.parametrize("mode", ["xls", "corrupt", "eleven", "hidden"])
def test_invalid_workbook(tmp_path, mode):
    path = tmp_path / ("input.xls" if mode == "xls" else "input.xlsx")
    if mode in {"xls", "corrupt"}:
        path.write_bytes(b"bad")
    else:
        workbook(path, 11 if mode == "eleven" else 1)
        if mode == "hidden":
            with ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            members["xl/workbook.xml"] = members["xl/workbook.xml"].replace(
                b'state="visible"', b'state="hidden"'
            )
            with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
    with pytest.raises(DomainError):
        inspect_workbook(path)
