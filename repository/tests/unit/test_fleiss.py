import numpy as np
import pytest
from statsmodels.stats.inter_rater import fleiss_kappa

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_agreement import data


@pytest.mark.parametrize(
    "rows",
    [
        [["a", "a", "b"], ["b", "b", "b"], ["a", "b", "b"], ["a", "a", "a"]],
        [["a", "a", "a"], ["b", "b", "b"]],
        [["a", "a", "a"]] * 20 + [["a", "a", "b"]],
    ],
)
def test_fleiss_reference(rows):
    current = data(rows)
    table = np.array([[row.count(category) for category in current.categories] for row in rows])
    settings = CriterionConfiguration("A", RatingType.NOMINAL, metrics=("fleiss_kappa",))
    expected = fleiss_kappa(table)
    assert execute_metrics(current, settings)[0].estimate == pytest.approx(expected)
    renamed = [[{"a": "x", "b": "y"}[value] for value in row] for row in rows]
    assert execute_metrics(data(renamed), settings)[0].estimate == pytest.approx(expected)


def test_fleiss_undefined():
    with pytest.raises(DomainError):
        execute_metrics(
            data([["a", "a", "a"]]),
            CriterionConfiguration("A", RatingType.NOMINAL, metrics=("fleiss_kappa",)),
        )
