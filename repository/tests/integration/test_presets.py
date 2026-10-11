import sqlite3
from dataclasses import replace

import pytest

from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.services import Services
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


def config():
    return AnalysisConfiguration(
        (CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("mae",)),)
    )


def test_named_permanent_presets_and_restart(tmp_path):
    services = Services.open(tmp_path)
    first = services.presets.create("First", config())
    second = services.presets.create("Second", config())
    assert len(Services.open(tmp_path).presets.list()) == 2
    assert first.id != second.id
    with pytest.raises(DomainError):
        services.presets.create("first", config())
    with services.database.connection() as conn:
        for sql in ('UPDATE presets SET name="Changed"', "DELETE FROM presets"):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql)


def test_apply_recalculates_range_and_warns_unmatched_types(tmp_path):
    services = Services.open(tmp_path)
    preset = services.presets.create("Range", config(), tolerance_fraction=0.1)
    current = continuous([[0, 10], [20, 30]])
    applied, warnings = services.presets.apply(preset.id, (current,))
    assert applied.criteria[0].tolerance == 3
    assert applied.criteria[0].metrics == ("mae",)
    applied, warnings = services.presets.apply(preset.id, (data([["a", "b"]]),))
    assert warnings
    assert applied.criteria[0].rating_type is RatingType.NOMINAL


def test_ordinal_match_mismatch_and_draft_selection(tmp_path):
    services = Services.open(tmp_path)
    ordinal = AnalysisConfiguration(
        (
            CriterionConfiguration(
                "A", RatingType.ORDINAL, ordinal_order=("b", "a"), metrics=("raw_agreement",)
            ),
        )
    )
    preset = services.presets.create("Ordered", ordinal)
    services.drafts.create("Study")
    services.presets.select(preset.id)
    assert services.drafts.active().preset_id == preset.id
    current = replace(data([["a", "b"]]), rating_type=RatingType.ORDINAL)
    applied, warnings = services.presets.apply(preset.id, (current,))
    assert applied.criteria[0].ordinal_order == ("b", "a")
    assert warnings == ()
    mismatch = replace(data([["a", "c"]]), rating_type=RatingType.ORDINAL)
    applied, warnings = services.presets.apply(preset.id, (mismatch,))
    assert applied.criteria[0].ordinal_order == ()
    assert any(w.code == "PRESET_ORDINAL_MISMATCH" for w in warnings)
