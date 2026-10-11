import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.uncertainty import preflight_uncertainty, results_with_ci
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


def test_wilson_reference_and_confidence():
    current = data([["a", "a"]] * 5 + [["a", "b"]] * 5)
    config = CriterionConfiguration("A", RatingType.NOMINAL, metrics=("pairwise_agreement",))
    result = results_with_ci(current, config, confidence=95, version_key="v1")[0]
    assert result.ci.method == "Wilson score"
    assert result.ci.lower == pytest.approx(23.659309, abs=1e-5)
    assert result.ci.upper == pytest.approx(76.340691, abs=1e-5)
    wider = results_with_ci(current, config, confidence=99, version_key="v1")[0]
    assert wider.ci.lower < result.ci.lower < result.ci.upper < wider.ci.upper


def test_bca_metric_deterministic():
    current = continuous([[i, i + (i % 4)] for i in range(40)])
    config = CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("mae",))
    first = results_with_ci(current, config, confidence=95, version_key="v1")
    assert first == results_with_ci(current, config, confidence=95, version_key="v1")
    assert first[0].ci.method == "BCa"
    assert first[0].bootstrap_resamples == 10000


def test_known_degenerate_ci_preflight():
    config = CriterionConfiguration("A", RatingType.CONTINUOUS, metrics=("mae",))
    findings = preflight_uncertainty(continuous([[1, 2], [2, 3], [3, 4]]), config)
    assert findings[0].code == "STAT_CI_UNDEFINED"
