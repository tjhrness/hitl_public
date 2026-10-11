import json
from pathlib import Path

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.icc import icc
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_continuous import continuous


def test_icc_independent_reference_and_row_order():
    fixtures = json.loads((Path(__file__).parents[1] / "golden/icc_reference.json").read_text())[
        "cases"
    ]
    for fixture in fixtures:
        for form in ("absolute", "consistency"):
            settings = CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=(f"icc_{form}",))
            result = execute_metrics(continuous(fixture["rows"]), settings)[0]
            assert result.estimate == pytest.approx(fixture[form])
            assert result.pair is None
            assert execute_metrics(continuous(list(reversed(fixture["rows"]))), settings)[
                0
            ].estimate == pytest.approx(result.estimate)


def test_icc_bias_and_degeneracy():
    current = continuous([[1, 4], [2, 5], [4, 7], [7, 10]])
    settings = CriterionConfiguration("A", RatingType.CONTINUOUS)
    assert icc(current, settings, consistency=True)[0].estimate == pytest.approx(1)
    assert icc(current, settings)[0].estimate < 1
    with pytest.raises(DomainError):
        icc(continuous([[1, 1], [1, 1]]), settings)
