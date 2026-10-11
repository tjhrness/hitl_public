"""Deterministic conventions, kept separate from numerical formulas."""

from dataclasses import replace

from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.metric_registry import MetricResult, get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion


def interpret(result: MetricResult, *, imbalanced: bool = False) -> MetricResult:
    key = get_registry().get(result.metric_id).interpretation_key
    value = result.estimate
    convention = "No universal categorical interpretation band."
    if key == "kappa":
        convention = "Landis–Koch convention; contextual judgment remains necessary."
        if value < 0:
            label = "Poor"
        else:
            label = next(
                (
                    label
                    for upper, label in (
                        (0.2, "Slight"),
                        (0.4, "Fair"),
                        (0.6, "Moderate"),
                        (0.8, "Substantial"),
                        (1, "Almost perfect"),
                    )
                    if value <= upper
                ),
                "Almost perfect",
            )
    elif key == "alpha":
        convention = "Krippendorff thresholds: 0.667 and 0.800."
        label = "Insufficient" if value < 0.667 else "Tentative" if value < 0.8 else "Reliable"
    elif key == "icc":
        convention = "ICC convention: 0.50, 0.75, 0.90; assess the CI and study design."
        label = (
            "Poor"
            if value < 0.5
            else "Moderate"
            if value < 0.75
            else "Good"
            if value < 0.9
            else "Excellent"
        )
    elif result.metric_id in ("mae", "rmse"):
        label = "Lower values mean smaller differences, in the original measurement units."
    elif key == "bland_altman":
        label = "Bias is first rater minus second; assess limits against practical requirements."
    elif key in ("ccc", "gwet"):
        label = "Values closer to 1 indicate greater agreement; assess uncertainty and context."
    else:
        label = "Higher percentages mean more item/pair observations agree under the stated rule."
    warnings = result.warnings
    if imbalanced and key == "kappa":
        warnings += ("Category prevalence can depress kappa; compare raw agreement and AC1/AC2.",)
    return replace(result, interpretation=label, convention=convention, warnings=warnings)


def interpret_results(
    results: tuple[MetricResult, ...], data: NormalizedCriterion
) -> tuple[MetricResult, ...]:
    imbalanced = any(
        f.code in ("WARNING_IMBALANCE", "WARNING_SEVERE_IMBALANCE") for f in quality_warnings(data)
    )
    return tuple(interpret(result, imbalanced=imbalanced) for result in results)
