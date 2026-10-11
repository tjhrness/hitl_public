"""Krippendorff nominal/ordinal alpha, complete-data coincidence formulation."""

from collections import Counter
from functools import partial
from itertools import combinations

from inter_rater_analyzer.categorical import complete_preflight, pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def alpha(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, ordinal: bool = False
) -> tuple[MetricResult, ...]:
    categories = settings.ordinal_order if ordinal else data.categories
    if set(categories) != set(data.categories) or len(categories) != len(data.categories):
        raise DomainError(ErrorCode.STAT_UNDEFINED, "Confirm the complete ordinal category order.")
    counts = Counter(value for row in data.values for value in row)
    total = counts.total()
    distance: dict[tuple[object, object], float] = {}
    for i, left in enumerate(categories):
        for j, right in enumerate(categories):
            low, high = sorted((i, j))
            distance[left, right] = (
                (
                    sum(counts[c] for c in categories[low : high + 1])
                    - (counts[left] + counts[right]) / 2
                )
                ** 2
                if ordinal
                else float(left != right)
            )
    observed = sum(distance[row[a], row[b]] for row in data.values for a, b in pairs(data))
    observed /= len(data.values) * len(pairs(data))
    expected = (
        2
        * sum(counts[a] * counts[b] * distance[a, b] for a, b in combinations(categories, 2))
        / (total * (total - 1))
    )
    if expected <= 0:
        raise DomainError(ErrorCode.STAT_UNDEFINED, "Alpha requires category variation.")
    identifier = "alpha_ordinal" if ordinal else "alpha_nominal"
    return (MetricResult(identifier, data.name, 1 - observed / expected),)


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, ordinal: bool = False
) -> tuple[ValidationFinding, ...]:
    findings = complete_preflight(data, settings)
    if findings:
        return findings
    try:
        alpha(data, settings, ordinal=ordinal)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_ALPHA_UNDEFINED",
                error.message,
                "Deselect alpha or provide category variation and category order.",
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    for ordinal in (False, True):
        identifier = "alpha_ordinal" if ordinal else "alpha_nominal"
        registry.register(
            MetricDefinition(
                identifier,
                "Krippendorff alpha",
                (RatingType.ORDINAL,) if ordinal else (RatingType.BINARY, RatingType.NOMINAL),
                MetricScope.OVERALL,
                True,
                ("Pairable data with category variation",),
                False,
                False,
                "alpha",
                "1 - observed / without-replacement expected disagreement. "
                "Ordinal distance uses squared cumulative pooled frequency between categories, "
                "with half endpoint frequencies; nominal distance is unequal-category indicator.",
                "1.0",
                partial(alpha, ordinal=ordinal),
                partial(preflight, ordinal=ordinal),
            )
        )
