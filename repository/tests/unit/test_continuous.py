import math
from dataclasses import replace

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.continuous import exclude_items
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_agreement import data


def continuous(rows):
    current = data(rows)
    return replace(current, rating_type=RatingType.CONTINUOUS, categories=())


def test_continuous_hand_calculations():
    current = continuous([[1, 2, 3], [3, 3, 5]])
    settings = CriterionConfiguration(
        "A", RatingType.CONTINUOUS, tolerance=1, metrics=("mae", "rmse", "practical_agreement")
    )
    results = execute_metrics(current, settings)
    mae = [r for r in results if r.metric_id == "mae"]
    rmse = [r for r in results if r.metric_id == "rmse"]
    assert [r.estimate for r in mae[1:]] == pytest.approx([0.5, 2, 1.5])
    assert mae[0].estimate == pytest.approx(4 / 3)
    assert rmse[0].estimate == pytest.approx((math.sqrt(0.5) + 2 + math.sqrt(2.5)) / 3)
    assert results[-1].estimate == 50


@pytest.mark.parametrize("raters", [2, 10])
def test_zero_range_and_exclusions(raters):
    current = continuous([[2] * raters, [9] * raters])
    filtered = exclude_items(current, {"1"})
    settings = CriterionConfiguration(
        "A", RatingType.CONTINUOUS, tolerance=0, metrics=("mae", "rmse", "practical_agreement")
    )
    assert [r.estimate for r in execute_metrics(filtered, settings)][-1] == 100
    assert filtered.minimum == filtered.maximum == 2
    assert execute_metrics(filtered, settings) == execute_metrics(
        continuous([[2] * raters]), settings
    )
