import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_continuous import continuous


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([[1, 1], [2, 2], [3, 3]], 1),
        ([[1, 2], [2, 3], [3, 4]], 4 / 7),
        ([[1, 2], [2, 4], [3, 6]], 4 / 11),
        ([[1, 3], [2, 2], [3, 1]], -1),
    ],
)
def test_ccc_hand_reference(rows, expected):
    config = CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("lin_ccc",))
    results = execute_metrics(continuous(rows), config)
    assert len(results) == 1 and results[0].pair is not None
    assert results[0].estimate == pytest.approx(expected)
    assert execute_metrics(continuous([list(reversed(row)) for row in rows]), config)[
        0
    ].estimate == pytest.approx(expected)


def test_constant_ccc_blocked():
    with pytest.raises(DomainError):
        execute_metrics(
            continuous([[1, 1], [1, 1]]),
            CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("lin_ccc",)),
        )
