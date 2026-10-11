import sqlite3

import pytest

from inter_rater_analyzer.domain import DomainError, VersionStatus, VersionType
from inter_rater_analyzer.services import Services


def test_versions_and_change_notes(tmp_path):
    services = Services.open(tmp_path)
    analysis, first = services.analyses.create("Study")
    assert first.number == 1
    assert services.analyses.get_version(first.id) == first
    services.analyses.finish(first.id, VersionStatus.ABANDONED)
    with pytest.raises(DomainError):
        services.analyses.new_version(analysis.id, VersionType.CONFIGURATION_ONLY, " ")
    second = services.analyses.new_version(analysis.id, VersionType.CONFIGURATION_ONLY, "Tolerance")
    assert second.number == 2
    services.analyses.update_draft_note(second.id, "Changed tolerance")
    assert services.analyses.get_version(second.id).change_note == "Changed tolerance"


@pytest.mark.parametrize("status", [VersionStatus.FAILED, VersionStatus.ABANDONED])
def test_terminal_versions_immutable_at_repository_and_sql_boundary(tmp_path, status):
    services = Services.open(tmp_path)
    _, version = services.analyses.create("Study")
    services.analyses.finish(version.id, status)
    with pytest.raises(DomainError):
        services.analyses.update_draft_note(version.id, "Illegal")
    with pytest.raises(DomainError):
        services.analyses.finish(version.id, status)
    with services.database.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE analysis_versions SET change_note=? WHERE id=?",
                ("Illegal", str(version.id)),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM analysis_versions WHERE id=?", (str(version.id),))
    assert services.analyses.get_version(version.id).status is status
