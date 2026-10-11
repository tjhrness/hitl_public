import json
from dataclasses import asdict, replace

import pytest

from inter_rater_analyzer.analytics import CriterionResult
from inter_rater_analyzer.comparison import compare_snapshots
from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.diagnostics import diagnose_items
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_registry import MetricResult
from tests.unit.test_agreement import data


def snapshot(rows, kind, score, metric="raw_agreement", tolerance=1):
    current = replace(data(rows), rating_type=kind)
    settings = CriterionConfiguration("A", kind, ordinal_order=(0, 1, 2, 3), tolerance=tolerance)
    result = CriterionResult(
        "A", (MetricResult(metric, "A", 50),), diagnose_items(current, settings), (), ()
    )
    return json.loads(
        json.dumps(
            {
                "data": [asdict(current)],
                "configuration": asdict(AnalysisConfiguration((settings,))),
                "result": {
                    "criteria": [asdict(result)],
                    "ranking": [{"item_id": "0", "score": score}],
                },
            },
            default=str,
        )
    )


@pytest.mark.parametrize(
    "kind,magnitude",
    [
        (RatingType.BINARY, 1),
        (RatingType.NOMINAL, 1),
        (RatingType.ORDINAL, 2),
        (RatingType.CONTINUOUS, 2),
    ],
)
def test_change_magnitudes_and_zero_priority(kind, magnitude):
    old = snapshot([[0, 0]], kind, "0")
    new = snapshot([[2, 0]], kind, "25", metric="pairwise_agreement")
    result = compare_snapshots(old, new)
    assert result.magnitudes == (("A", magnitude),)
    assert result.priorities[0].change == 25
    assert result.priorities[0].percent_change is None
    assert result.metrics == ()


@pytest.mark.parametrize("tolerance,material", [(1, False), (0.99, True)])
def test_continuous_strict_latest_tolerance(tolerance, material):
    old = snapshot([[0, 0]], RatingType.CONTINUOUS, "25", tolerance=0)
    new = snapshot([[2, 0]], RatingType.CONTINUOUS, "50", tolerance=tolerance)
    result = compare_snapshots(old, new)
    assert result.consensus[0].material is material
    assert result.priorities[0].percent_change == 100


def test_consensus_category_and_tie_transitions():
    old = snapshot([[0, 0], [1, 2]], RatingType.NOMINAL, "25")
    new = snapshot([[1, 1], [1, 1]], RatingType.NOMINAL, "25")
    result = compare_snapshots(old, new)
    assert [(c.previous, c.latest) for c in result.consensus] == [(0, 1), (None, 1)]


def test_removed_ordinal_label_has_no_defensible_step_distance():
    old = snapshot([[0, 1]], RatingType.ORDINAL, "25")
    new = snapshot([[2, 1]], RatingType.ORDINAL, "25")
    new["configuration"]["criteria"][0]["ordinal_order"] = [1, 2]
    result = compare_snapshots(old, new)
    assert result.cells[0].magnitude is None
    assert result.magnitudes == (("A", None),)
