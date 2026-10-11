from dataclasses import replace

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.diagnostics import diagnose_items
from inter_rater_analyzer.domain import RatingType
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


def test_mode_ties_and_frequencies():
    current = data([["a", "a", "b", "b"], ["a", "a", "a", "b"]])
    results = diagnose_items(current, CriterionConfiguration("A", RatingType.NOMINAL))
    assert results[0].consensus_label == "No consensus"
    assert results[0].consensus is None
    assert results[1].consensus == "a"
    assert results[1].modal_share == 0.75
    assert results[1].frequencies == (("a", 3), ("b", 1))


def test_continuous_median_and_ordinal_near_agreement():
    current = continuous([[1, 2, 4, 9]])
    assert (
        diagnose_items(current, CriterionConfiguration("A", RatingType.CONTINUOUS))[0].consensus
        == 3
    )
    ordinal = replace(data([["low", "mid", "high"]]), rating_type=RatingType.ORDINAL)
    result = diagnose_items(
        ordinal,
        CriterionConfiguration("A", RatingType.ORDINAL, ordinal_order=("low", "mid", "high")),
    )[0]
    assert result.consensus_label == "No consensus"
    assert result.near_agreement == 200 / 3
