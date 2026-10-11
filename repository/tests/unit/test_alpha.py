from dataclasses import replace

import krippendorff
import numpy as np
import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_agreement import data


@pytest.mark.parametrize("level", ["nominal", "ordinal"])
@pytest.mark.parametrize(
    "rows",
    [
        [[0, 0, 1], [1, 1, 2], [2, 2, 2], [0, 1, 2]],
        [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
    ],
)
def test_alpha_independent_reference(rows, level):
    kind = RatingType.ORDINAL if level == "ordinal" else RatingType.NOMINAL
    current = replace(data(rows), rating_type=kind)
    settings = CriterionConfiguration(
        "A", kind, ordinal_order=(0.0, 1.0, 2.0), metrics=(f"alpha_{level}",)
    )
    expected = krippendorff.alpha(
        reliability_data=np.array(rows).T, level_of_measurement=level, value_domain=[0, 1, 2]
    )
    assert execute_metrics(current, settings)[0].estimate == pytest.approx(expected)
    assert execute_metrics(replace(current, values=tuple(reversed(current.values))), settings)[
        0
    ].estimate == pytest.approx(expected)


def test_alpha_undefined():
    with pytest.raises(DomainError):
        execute_metrics(
            data([["a", "a"]]),
            CriterionConfiguration("A", RatingType.NOMINAL, metrics=("alpha_nominal",)),
        )
