import pytest

from inter_rater_analyzer.interpretation import interpret
from inter_rater_analyzer.metric_registry import MetricResult


@pytest.mark.parametrize(
    "metric,value,label",
    [
        ("cohen_kappa", -0.1, "Poor"),
        ("cohen_kappa", 0, "Slight"),
        ("cohen_kappa", 0.2, "Slight"),
        ("cohen_kappa", 0.4, "Fair"),
        ("cohen_kappa", 0.6, "Moderate"),
        ("cohen_kappa", 0.8, "Substantial"),
        ("cohen_kappa", 0.81, "Almost perfect"),
        ("alpha_nominal", 0.6669, "Insufficient"),
        ("alpha_nominal", 0.667, "Tentative"),
        ("alpha_nominal", 0.8, "Reliable"),
        ("icc_absolute", 0.499, "Poor"),
        ("icc_absolute", 0.5, "Moderate"),
        ("icc_absolute", 0.75, "Good"),
        ("icc_absolute", 0.9, "Excellent"),
    ],
)
def test_exact_interpretation_boundaries(metric, value, label):
    result = interpret(MetricResult(metric, "A", value))
    assert result.interpretation == label
    assert result.convention


def test_unbanded_metrics_and_prevalence():
    result = interpret(MetricResult("mae", "A", 0.1))
    assert "Lower" in result.interpretation
    gwet = interpret(MetricResult("gwet_ac1", "A", 0.8))
    assert "universal" in gwet.convention
    kappa = interpret(MetricResult("cohen_kappa", "A", 0.1), imbalanced=True)
    assert "AC1/AC2" in kappa.warnings[-1]
