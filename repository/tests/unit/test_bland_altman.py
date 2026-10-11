import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_continuous import continuous


def test_bland_altman_hand_calculation_and_sign():
    config = CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("bland_altman",))
    result = execute_metrics(continuous([[1, 1], [3, 2], [5, 3]]), config)[0]
    assert result.estimate == 1
    assert result.bland_altman.means == (1, 2.5, 4)
    assert result.bland_altman.differences == (0, 1, 2)
    assert result.bland_altman.sd == 1
    assert result.bland_altman.lower == pytest.approx(-0.96)
    assert result.bland_altman.upper == pytest.approx(2.96)
    assert result.adjusted_p is None


@pytest.mark.parametrize("rows,bias", [([[1, 1], [2, 2]], 0), ([[1, 3], [2, 4]], -2)])
def test_constant_difference_valid(rows, bias):
    result = execute_metrics(
        continuous(rows),
        CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("bland_altman",)),
    )[0]
    assert result.estimate == bias
    assert result.bland_altman.lower == result.bland_altman.upper == bias


def test_single_item_blocked():
    with pytest.raises(DomainError):
        execute_metrics(
            continuous([[1, 2]]),
            CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("bland_altman",)),
        )
