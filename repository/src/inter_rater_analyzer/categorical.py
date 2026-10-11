"""Pure categorical point estimates, independent of Qt and persistence."""

from itertools import combinations

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import MetricScope, RatingType, ValidationSeverity
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import (
    ConfusionMatrix,
    MetricDefinition,
    MetricRegistry,
    MetricResult,
)
from inter_rater_analyzer.ratings import NormalizedCriterion


def pairs(data: NormalizedCriterion) -> tuple[tuple[int, int], ...]:
    return tuple(combinations(range(len(data.raters)), 2))


def complete_preflight(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
) -> tuple[ValidationFinding, ...]:
    if (
        not data.values
        or len(data.raters) < 2
        or any(len(row) != len(data.raters) for row in data.values)
        or any(f.severity is ValidationSeverity.ERROR for f in data.findings)
    ):
        return (
            ValidationFinding(
                "STAT_INCOMPLETE",
                "Complete ratings are required.",
                "Provide at least one item and two complete raters.",
            ),
        )
    return ()


def pairwise_agreement(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
) -> tuple[MetricResult, ...]:
    return tuple(
        MetricResult(
            "pairwise_agreement",
            data.name,
            100 * sum(row[a] == row[b] for row in data.values) / len(data.values),
            (data.raters[a], data.raters[b]),
        )
        for a, b in pairs(data)
    )


def raw_agreement(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
) -> tuple[MetricResult, ...]:
    results = pairwise_agreement(data, settings)
    return (
        MetricResult("raw_agreement", data.name, sum(r.estimate for r in results) / len(results)),
    )


def confusion_matrices(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
) -> tuple[MetricResult, ...]:
    categories = data.categories
    results: list[MetricResult] = []
    for a, b in pairs(data):
        counts = tuple(
            tuple(sum(row[a] == x and row[b] == y for row in data.values) for y in categories)
            for x in categories
        )
        correct = sum(counts[i][i] for i in range(len(categories)))
        results.append(
            MetricResult(
                "confusion_matrix",
                data.name,
                100 * correct / len(data.values),
                (data.raters[a], data.raters[b]),
                confusion=ConfusionMatrix(categories, counts),
            )
        )
    return tuple(results)


def register_metrics(registry: MetricRegistry) -> None:
    kinds = (RatingType.BINARY, RatingType.NOMINAL, RatingType.ORDINAL)
    for identifier, name, scope, calculate in (
        ("raw_agreement", "Overall exact agreement (%)", MetricScope.OVERALL, raw_agreement),
        (
            "pairwise_agreement",
            "Pairwise exact agreement (%)",
            MetricScope.PAIRWISE,
            pairwise_agreement,
        ),
        ("confusion_matrix", "Pairwise confusion matrix", MetricScope.PAIRWISE, confusion_matrices),
    ):
        registry.register(
            MetricDefinition(
                identifier,
                name,
                kinds,
                scope,
                identifier == "raw_agreement",
                ("Complete ratings",),
                False,
                False,
                "raw_agreement",
                "Exact equality over item × rater-pair observations; percentage.",
                "1.0",
                calculate,
                complete_preflight,
            )
        )
