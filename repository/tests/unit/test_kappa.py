from dataclasses import replace

import numpy as np
import pytest
from statsmodels.stats.inter_rater import cohens_kappa

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_agreement import data


@pytest.mark.parametrize(
    "variant,weight",
    [("cohen_kappa", None), ("linear_kappa", "linear"), ("quadratic_kappa", "quadratic")],
)
def test_independent_kappa_reference_and_symmetry(variant, weight):
    rows = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "c"], ["c", "c"], ["c", "a"]]
    current = replace(data(rows), rating_type=RatingType.ORDINAL)
    settings = CriterionConfiguration(
        "A", RatingType.ORDINAL, ordinal_order=("a", "b", "c"), metrics=(variant,)
    )
    table = np.array([[1, 1, 0], [0, 1, 1], [1, 0, 1]])
    expected = cohens_kappa(table, wt=weight, return_results=False)
    assert execute_metrics(current, settings)[0].estimate == pytest.approx(expected)
    swapped = replace(current, values=tuple(tuple(reversed(row)) for row in current.values))
    assert execute_metrics(swapped, settings)[0].estimate == pytest.approx(expected)


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([["a", "a"], ["b", "b"]], 1),
        ([["a", "b"], ["b", "a"]], -1),
        ([["a", "a"], ["a", "b"], ["b", "a"], ["b", "b"]], 0),
    ],
)
def test_kappa_hand_values(rows, expected):
    settings = CriterionConfiguration("A", RatingType.NOMINAL, metrics=("cohen_kappa",))
    assert execute_metrics(data(rows), settings)[0].estimate == pytest.approx(expected)


def test_degenerate_kappa_blocked():
    with pytest.raises(DomainError):
        execute_metrics(
            data([["a", "a"], ["a", "a"]]),
            CriterionConfiguration("A", RatingType.NOMINAL, metrics=("cohen_kappa",)),
        )
