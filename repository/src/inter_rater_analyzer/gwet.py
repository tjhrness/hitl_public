"""Gwet AC1 and quadratically weighted AC2 for complete fixed panels."""

from collections import Counter
from functools import partial

from inter_rater_analyzer.categorical import complete_preflight, pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def gwet(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, ordinal: bool = False
) -> tuple[MetricResult, ...]:
    categories = settings.ordinal_order if ordinal else data.categories
    q = len(categories)
    if q < 2 or set(categories) != set(data.categories) or q != len(data.categories):
        raise DomainError(
            ErrorCode.STAT_UNDEFINED,
            "AC requires at least two categories and a valid ordinal order if used.",
        )
    weights = {
        (a, b): 1 - ((i - j) / (q - 1)) ** 2 if ordinal else float(i == j)
        for i, a in enumerate(categories)
        for j, b in enumerate(categories)
    }
    observed = sum(weights[row[a], row[b]] for row in data.values for a, b in pairs(data))
    observed /= len(data.values) * len(pairs(data))
    counts = Counter(value for row in data.values for value in row)
    total = counts.total()
    expected = (
        sum(weights.values())
        * sum((count / total) * (1 - count / total) for count in counts.values())
        / (q * (q - 1))
    )
    if expected >= 1:
        raise DomainError(ErrorCode.STAT_UNDEFINED, "AC chance-agreement denominator is undefined.")
    return (
        MetricResult(
            "gwet_ac2" if ordinal else "gwet_ac1", data.name, (observed - expected) / (1 - expected)
        ),
    )


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, ordinal: bool = False
) -> tuple[ValidationFinding, ...]:
    findings = complete_preflight(data, settings)
    if findings:
        return findings
    try:
        gwet(data, settings, ordinal=ordinal)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_AC_UNDEFINED", error.message, "Deselect AC or supply a valid category domain."
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    for ordinal in (False, True):
        registry.register(
            MetricDefinition(
                "gwet_ac2" if ordinal else "gwet_ac1",
                "Gwet AC2" if ordinal else "Gwet AC1",
                (RatingType.ORDINAL,) if ordinal else (RatingType.BINARY, RatingType.NOMINAL),
                MetricScope.OVERALL,
                True,
                ("At least two categories",),
                False,
                False,
                "gwet",
                "(Pa-Pe)/(1-Pe); Pa is mean item/pair agreement weight; "
                "Pe=sum(weights)*sum(p*(1-p))/(q*(q-1)); "
                "AC1 uses identity weights, AC2 uses 1-((rank_a-rank_b)/(q-1))^2.",
                "1.0",
                partial(gwet, ordinal=ordinal),
                partial(preflight, ordinal=ordinal),
            )
        )
