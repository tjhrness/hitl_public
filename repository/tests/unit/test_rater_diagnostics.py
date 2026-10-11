from dataclasses import replace

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.rater_diagnostics import diagnose_raters
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


def test_nominal_distribution_outliers_and_no_direction():
    current = data([["a", "a", "b"], ["b", "b", "b"]])
    results = diagnose_raters(current, CriterionConfiguration("A", RatingType.NOMINAL))
    assert results[2].agreement == 50
    assert results[2].disagreement == 50
    assert results[2].outlier_frequency == 50
    assert results[2].distribution == (("a", 0.0), ("b", 1.0))
    assert results[2].direction is None
    assert results[2].variance is None


def test_ordered_direction_and_spread():
    current = continuous([[0, 1, 2], [1, 2, 3]])
    results = diagnose_raters(current, CriterionConfiguration("A", RatingType.CONTINUOUS))
    assert [r.direction for r in results] == [-1, 0, 1]
    assert results[0].variance == 0.25
    assert results[0].spread == 1
    assert results[0].disagreement == 100
    ordinal = replace(data([["a", "b", "c"]]), rating_type=RatingType.ORDINAL)
    result = diagnose_raters(
        ordinal, CriterionConfiguration("A", RatingType.ORDINAL, ordinal_order=("a", "b", "c"))
    )
    assert [r.direction for r in result] == [-1, 0, 1]
    assert result[0].disagreement == pytest.approx(75)


def test_identical_raters():
    results = diagnose_raters(
        data([["a", "a"], ["b", "b"]]), CriterionConfiguration("A", RatingType.NOMINAL)
    )
    assert all(r.agreement == 100 and r.disagreement == 0 for r in results)
    assert all(r.outlier_frequency == 0 for r in results)
