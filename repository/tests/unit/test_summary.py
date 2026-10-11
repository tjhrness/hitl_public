from dataclasses import replace
from decimal import Decimal

from inter_rater_analyzer.analytics import CriterionResult
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.diagnostics import diagnose_items
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_registry import MetricResult
from inter_rater_analyzer.priority import ItemPriority
from inter_rater_analyzer.rater_diagnostics import diagnose_raters
from inter_rater_analyzer.summary import executive_summary
from tests.unit.test_agreement import data
from tests.unit.test_continuous import continuous


def test_warning_rules_and_top_priority():
    current = data([["a", "a"]] * 9 + [["a", "b"]])
    metric = MetricResult(
        "cohen_kappa",
        "A",
        0.2,
        interpretation="Slight",
        warnings=("Category prevalence can depress kappa.", "Review suitability."),
    )
    result = CriterionResult("A", (metric,), (), (), ())
    entries = executive_summary((result,), (current,), (ItemPriority("x", 1, Decimal(75), ()),))
    assert [entry.rule_id for entry in entries] == [
        "WARNING_SAMPLE_SIZE",
        "WARNING_SEVERE_IMBALANCE",
        "CONCERNING_AGREEMENT",
        "KAPPA_PREVALENCE",
        "METRIC_SUITABILITY",
        "HIGHEST_PRIORITY",
    ]
    assert all(entry.why for entry in entries)


def test_same_measure_comparison_and_ordered_tendency():
    current = continuous([[0, 1, 2], [1, 2, 3]])
    settings = CriterionConfiguration("A", RatingType.CONTINUOUS)
    results = (
        CriterionResult(
            "A", (), diagnose_items(current, settings), diagnose_raters(current, settings), ()
        ),
    )
    entries = executive_summary(results, (current,), ())
    assert sum(entry.rule_id == "ORDERED_DIRECTION" for entry in entries) == 2
    nominal = data([["a", "b"], ["a", "a"]])
    results = tuple(
        CriterionResult(name, (MetricResult("raw_agreement", name, value),), (), (), ())
        for name, value in (("A", 50), ("B", 75))
    )
    entries = executive_summary(results, (nominal, replace(nominal, name="B")), ())
    comparison = [e for e in entries if e.rule_id == "CRITERION_COMPARISON"]
    assert len(comparison) == 1
    assert comparison[0].message == "B has higher observed exact agreement than A."


def test_summary_deterministic_observed_thresholds_and_nominal_language():
    current = data([["a", "b"], ["a", "a"]])
    settings = CriterionConfiguration("A", RatingType.NOMINAL)
    result = CriterionResult(
        "A", (), diagnose_items(current, settings), diagnose_raters(current, settings), ()
    )
    summary = executive_summary((result,), (current,), ())
    assert [entry.rule_id for entry in summary] == ["WARNING_SAMPLE_SIZE", "NO_CONSENSUS"]
    assert summary[0].why == "2 included items; fewer than 30 may yield unstable estimates."
    assert summary[1].why == "1/2 items (50%) have tied modes; trigger: count > 0."
    assert summary == executive_summary((result,), (current,), ())
    assert not any("strict" in entry.message or "lenient" in entry.message for entry in summary)


def test_comparisons_require_same_metric_and_type():
    current = data([["a", "b"], ["a", "a"]])
    results = (
        CriterionResult("A", (MetricResult("raw_agreement", "A", 50),), (), (), ()),
        CriterionResult("B", (MetricResult("gwet_ac1", "B", 0.9),), (), (), ()),
    )
    summary = executive_summary(results, (current,), ())
    assert not any(entry.rule_id == "CRITERION_COMPARISON" for entry in summary)
