from dataclasses import replace

import numpy as np
import pytest
from statsmodels.stats.inter_rater import cohens_kappa
from statsmodels.stats.multitest import multipletests

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from inter_rater_analyzer.significance import add_significance, holm
from tests.unit.test_agreement import data


def test_holm_reference_and_order():
    values = (0.04, 0.001, 0.03, 0.2)
    assert holm(values) == pytest.approx(multipletests(values, method="holm")[1])
    assert holm(()) == ()
    with pytest.raises(ValueError):
        holm((float("nan"),))


def test_cohen_pvalue_independent_and_no_raw_public_values():
    current = data([["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]] * 10)
    config = CriterionConfiguration(
        "A", RatingType.NOMINAL, metrics=("cohen_kappa", "raw_agreement")
    )
    results = add_significance(execute_metrics(current, config), current)
    expected = cohens_kappa(np.array([[10, 10], [0, 20]])).pvalue_two_sided
    assert results[0].adjusted_p == pytest.approx(expected)
    assert results[1].adjusted_p is None
    assert not hasattr(results[0], "raw_p")


def test_holm_pair_family_isolation():
    current = data([["a", "a", "b"], ["a", "b", "b"], ["b", "b", "a"], ["b", "b", "b"]] * 10)
    config = CriterionConfiguration("A", RatingType.NOMINAL, metrics=("cohen_kappa",))
    original = execute_metrics(current, config)
    extra = replace(original[0], criterion="Other criterion")
    corrected = add_significance(original + (extra,), current)
    probabilities = []
    for result in original:
        a, b = (current.raters.index(alias) for alias in result.pair)
        table = np.array(
            [
                [
                    sum(row[a] == x and row[b] == y for row in current.values)
                    for y in current.categories
                ]
                for x in current.categories
            ]
        )
        probabilities.append(cohens_kappa(table).pvalue_two_sided)
    assert [r.adjusted_p for r in corrected[:-1]] == pytest.approx(holm(tuple(probabilities)))
    assert corrected[-1] == extra
