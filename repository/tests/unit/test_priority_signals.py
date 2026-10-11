from dataclasses import replace

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.configuration import PrioritySignal as S
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.priority_signals import priority_signals
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


@pytest.mark.parametrize("kind", [RatingType.BINARY, RatingType.NOMINAL])
def test_categorical_signals(kind):
    current = replace(data([["a", "b"], ["a", "a"]]), rating_type=kind)
    results = priority_signals(current, CriterionConfiguration("A", kind))
    first = {s.signal: s.normalized for s in results[0].signals}
    assert first == {
        S.PAIRWISE: 100,
        S.INVERSE_CONSENSUS: 50,
        S.SPREAD: 100,
        S.DEVIATION: None,
        S.OUTLIER: 0,
        S.NO_CONSENSUS: 100,
    }
    assert all(s.normalized in (0, None) for s in results[1].signals)


def test_ordinal_hand_calculation():
    current = replace(data([["a", "b", "c"]]), rating_type=RatingType.ORDINAL)
    result = priority_signals(
        current, CriterionConfiguration("A", RatingType.ORDINAL, ordinal_order=("a", "b", "c"))
    )[0]
    values = {s.signal: s.normalized for s in result.signals}
    assert values[S.PAIRWISE] == pytest.approx(200 / 3)
    assert values[S.INVERSE_CONSENSUS] == pytest.approx(200 / 3)
    assert values[S.SPREAD] == 100
    assert values[S.DEVIATION] == pytest.approx(100 / 3)
    assert values[S.NO_CONSENSUS] == 100


def test_continuous_tolerance_boundary_range_and_inapplicable():
    result = priority_signals(
        continuous([[0, 1, 2]]), CriterionConfiguration("A", RatingType.CONTINUOUS, tolerance=1)
    )[0]
    values = {s.signal: s.normalized for s in result.signals}
    assert values[S.PAIRWISE] == pytest.approx(100 / 3)
    assert values[S.SPREAD] == 100
    assert values[S.DEVIATION] == pytest.approx(100 / 3)
    assert values[S.INVERSE_CONSENSUS] is None
    assert values[S.NO_CONSENSUS] is None


@pytest.mark.parametrize("kind", list(RatingType))
def test_constant_domain(kind):
    current = replace(data([[1, 1, 1]]), rating_type=kind)
    result = priority_signals(current, CriterionConfiguration("A", kind, ordinal_order=(1,)))[0]
    assert all(s.normalized in (0, None) for s in result.signals)
