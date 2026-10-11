"""Continuous descriptive agreement with complete rows as the sampling unit."""

import math
from dataclasses import replace
from functools import partial

from inter_rater_analyzer.categorical import complete_preflight, pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def exclude_items(data: NormalizedCriterion, excluded: set[str]) -> NormalizedCriterion:
    kept = [
        (item, row)
        for item, row in zip(data.item_ids, data.values, strict=True)
        if item not in excluded
    ]
    if not kept:
        raise DomainError(ErrorCode.VALIDATION_VALUE, "Keep at least one included item.")
    numbers = [
        float(value)
        for _, row in kept
        for value in row
        if data.rating_type is RatingType.CONTINUOUS
    ]
    return replace(
        data,
        item_ids=tuple(item for item, _ in kept),
        values=tuple(row for _, row in kept),
        minimum=min(numbers) if numbers else None,
        maximum=max(numbers) if numbers else None,
    )


def continuous_preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ValidationFinding, ...]:
    findings = complete_preflight(data, settings)
    if findings:
        return findings
    if any(
        isinstance(value, str) or not math.isfinite(value) for row in data.values for value in row
    ):
        return (
            ValidationFinding(
                "STAT_NUMERIC",
                "Continuous ratings must be finite numbers.",
                "Resolve numeric rating findings.",
            ),
        )
    if not math.isfinite(settings.tolerance) or settings.tolerance < 0:
        return (
            ValidationFinding(
                "STAT_TOLERANCE",
                "Tolerance must be finite and nonnegative.",
                "Set a nonnegative tolerance.",
            ),
        )
    return ()


def error_metric(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, squared: bool = False
) -> tuple[MetricResult, ...]:
    results: list[MetricResult] = []
    identifier = "rmse" if squared else "mae"
    for a, b in pairs(data):
        errors = [abs(float(row[a]) - float(row[b])) for row in data.values]
        estimate = (
            math.sqrt(sum(e * e for e in errors) / len(errors))
            if squared
            else sum(errors) / len(errors)
        )
        results.append(
            MetricResult(identifier, data.name, estimate, (data.raters[a], data.raters[b]))
        )
    overall = MetricResult(identifier, data.name, sum(r.estimate for r in results) / len(results))
    return overall, *results


def practical_agreement(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[MetricResult, ...]:
    agreed = sum(
        abs(float(row[a]) - float(row[b])) <= settings.tolerance
        for row in data.values
        for a, b in pairs(data)
    )
    return (
        MetricResult(
            "practical_agreement", data.name, 100 * agreed / (len(data.values) * len(pairs(data)))
        ),
    )


def register_metrics(registry: MetricRegistry) -> None:
    for identifier, calculate in (
        ("mae", partial(error_metric, squared=False)),
        ("rmse", partial(error_metric, squared=True)),
        ("practical_agreement", practical_agreement),
    ):
        registry.register(
            MetricDefinition(
                identifier,
                identifier.replace("_", " ").title(),
                (RatingType.CONTINUOUS,),
                MetricScope.OVERALL if identifier == "practical_agreement" else MetricScope.BOTH,
                True,
                ("Finite complete numeric ratings",),
                False,
                False,
                "continuous_error",
                "Per-pair MAE/RMSE; panel values are arithmetic means of pair estimates. "
                "Practical agreement counts absolute differences <= tolerance as a percentage.",
                "1.0",
                calculate,
                continuous_preflight,
            )
        )
