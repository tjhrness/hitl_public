from decimal import Decimal

import pytest

from inter_rater_analyzer.configuration import PrioritySignal as S
from inter_rater_analyzer.configuration import SignalWeight
from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.priority import rank_items
from inter_rater_analyzer.priority_signals import ItemSignals, SignalValue


def signals(criterion, item, a, b):
    return ItemSignals(
        criterion,
        item,
        (
            SignalValue(S.SPREAD, a / 100, a),
            SignalValue(S.INVERSE_CONSENSUS, None if b is None else b / 100, b),
        ),
    )


def test_equal_criteria_renormalization_and_explanation():
    weights = (
        SignalWeight(S.SPREAD, Decimal("33.3")),
        SignalWeight(S.INVERSE_CONSENSUS, Decimal("66.7")),
    )
    results = rank_items(((signals("A", "x", 100, None),), (signals("B", "x", 0, 100),)), weights)
    result = results[0]
    assert result.score == Decimal("83.35")
    assert result.criteria[0].contributions[0].effective_weight == 100
    assert result.criteria[0].contributions[1].effective_weight == 0
    for criterion in result.criteria:
        assert sum(c.contribution for c in criterion.contributions) == criterion.score
        assert sum(c.effective_weight for c in criterion.contributions) == 100


def test_ties_and_bounds():
    results = rank_items(
        (tuple(signals("A", i, 0, 0) for i in ("z", "a", "A")),),
        (SignalWeight(S.SPREAD, Decimal(100)),),
    )
    assert [(r.item_id, r.rank) for r in results] == [("A", 1), ("a", 2), ("z", 3)]
    assert all(0 <= r.score <= 100 for r in results)


def test_inapplicable_or_invalid_weights_block():
    rows = ((signals("A", "x", 100, None),),)
    with pytest.raises(DomainError):
        rank_items(rows, (SignalWeight(S.INVERSE_CONSENSUS, Decimal(100)),))
    with pytest.raises(DomainError):
        rank_items(rows, (SignalWeight(S.SPREAD, Decimal("99.9")),))
