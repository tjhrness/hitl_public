from dataclasses import replace

import pytest

from inter_rater_analyzer.domain import DomainError, VersionStatus
from inter_rater_analyzer.services import Services
from tests.unit.test_configuration import configured
from tests.workbook_fixtures.builders import workbook


def test_single_draft_restart_and_abandonment(tmp_path):
    services = Services.open(tmp_path)
    draft = services.drafts.create("Draft study")
    with pytest.raises(DomainError):
        services.drafts.create("Other")
    config, _ = configured()
    changed = replace(
        draft,
        configuration=config,
        acknowledged_warnings=("WARNING_SAMPLE_SIZE",),
        types_locked=True,
    )
    services.drafts.save(changed)
    restarted = Services.open(tmp_path)
    assert restarted.drafts.active() == changed
    restarted.drafts.abandon(draft.version_id)
    assert restarted.drafts.active() is None
    assert restarted.analyses.get_version(draft.version_id).status is VersionStatus.ABANDONED
    with pytest.raises(DomainError):
        restarted.drafts.save(changed)
    assert restarted.drafts.create("New").version_id != draft.version_id


def test_draft_workbook_restored_without_original_source(tmp_path):
    services = Services.open(tmp_path / "state")
    services.drafts.create("Study")
    source = workbook(tmp_path / "input.xlsx")
    imported = services.drafts.attach_workbook(source)
    source.unlink()
    restarted = Services.open(tmp_path / "state")
    assert restarted.drafts.active().workbook_id == imported.inspection.artifact_id
    assert restarted.drafts.resume_workbook() == imported
