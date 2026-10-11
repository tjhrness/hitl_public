"""Bland–Altman pair summaries. Difference is first alias minus second alias."""

from statistics import mean, stdev

from inter_rater_analyzer.categorical import pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.continuous import continuous_preflight
from inter_rater_analyzer.domain import MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import (
    BlandAltmanData,
    MetricDefinition,
    MetricRegistry,
    MetricResult,
)
from inter_rater_analyzer.ratings import NormalizedCriterion


def calculate(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[MetricResult, ...]:
    results: list[MetricResult] = []
    for a, b in pairs(data):
        means = tuple((float(row[a]) + float(row[b])) / 2 for row in data.values)
        differences = tuple(float(row[a]) - float(row[b]) for row in data.values)
        bias, sd = mean(differences), stdev(differences)
        results.append(
            MetricResult(
                "bland_altman",
                data.name,
                bias,
                (data.raters[a], data.raters[b]),
                bland_altman=BlandAltmanData(
                    data.item_ids, means, differences, sd, bias - 1.96 * sd, bias + 1.96 * sd
                ),
            )
        )
    return tuple(results)


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ValidationFinding, ...]:
    findings = continuous_preflight(data, settings)
    if findings:
        return findings
    if len(data.values) < 2:
        return (
            ValidationFinding(
                "STAT_BA_SAMPLE",
                "Bland–Altman requires two or more items.",
                "Include at least two items.",
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    registry.register(
        MetricDefinition(
            "bland_altman",
            "Bland–Altman analysis",
            (RatingType.CONTINUOUS,),
            MetricScope.PAIRWISE,
            True,
            ("At least two items",),
            False,
            False,
            "bland_altman",
            "Difference=first alias minus second; sample SD (n-1); "
            "limits=bias ± 1.96*SD. Limits describe differences, not a confidence interval.",
            "1.0",
            calculate,
            preflight,
        )
    )
