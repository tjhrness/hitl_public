import json
from dataclasses import replace
from pathlib import Path

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_execution import execute_metrics
from tests.unit.test_agreement import data

FIXTURES = json.loads((Path(__file__).parents[1] / "golden/gwet_reference.json").read_text())[
    "cases"
]


@pytest.mark.parametrize("fixture", FIXTURES)
def test_gwet_independent_reference(fixture):
    ordinal = fixture["weighting"] == "quadratic"
    kind = RatingType.ORDINAL if ordinal else RatingType.NOMINAL
    current = replace(data(fixture["rows"]), rating_type=kind)
    settings = CriterionConfiguration(
        "A",
        kind,
        ordinal_order=current.categories,
        metrics=("gwet_ac2" if ordinal else "gwet_ac1",),
    )
    assert execute_metrics(current, settings)[0].estimate == pytest.approx(
        fixture["estimate"], abs=1e-11
    )
