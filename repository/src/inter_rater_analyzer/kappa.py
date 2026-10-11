"""Cohen kappa via observed/independent-marginal disagreement ratios."""

from collections import Counter
from functools import partial

from inter_rater_analyzer.categorical import complete_preflight, pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating


def cohen(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
    *,
    power: int = 0,
) -> tuple[MetricResult, ...]:
    categories = settings.ordinal_order if power else data.categories
    if power and (
        set(categories) != set(data.categories) or len(categories) != len(data.categories)
    ):
        raise DomainError(ErrorCode.STAT_UNDEFINED, "Confirm the ordinal category order.")
    ranks = {category: index for index, category in enumerate(categories)}

    def distance(left: Rating, right: Rating) -> float:
        if not power:
            return float(left != right)
        return float(abs(ranks[left] - ranks[right]) ** power)

    results: list[MetricResult] = []
    identifier = {0: "cohen_kappa", 1: "linear_kappa", 2: "quadratic_kappa"}[power]
    n = len(data.values)
    for a, b in pairs(data):
        left = Counter(row[a] for row in data.values)
        right = Counter(row[b] for row in data.values)
        observed = sum(distance(row[a], row[b]) for row in data.values) / n
        expected = (
            sum(distance(x, y) * nx * right[y] for x, nx in left.items() for y in right) / n**2
        )
        if expected <= 0:
            raise DomainError(
                ErrorCode.STAT_UNDEFINED, "Kappa is undefined for degenerate marginal ratings."
            )
        results.append(
            MetricResult(
                identifier, data.name, 1 - observed / expected, (data.raters[a], data.raters[b])
            )
        )
    return tuple(results)


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, power: int = 0
) -> tuple[ValidationFinding, ...]:
    findings = complete_preflight(data, settings)
    if findings:
        return findings
    try:
        cohen(data, settings, power=power)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_KAPPA_UNDEFINED",
                error.message,
                "Deselect this metric or provide nondegenerate data.",
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    for identifier, power in (("cohen_kappa", 0), ("linear_kappa", 1), ("quadratic_kappa", 2)):
        kinds = (
            (RatingType.ORDINAL,)
            if power
            else (RatingType.BINARY, RatingType.NOMINAL, RatingType.ORDINAL)
        )
        registry.register(
            MetricDefinition(
                identifier,
                identifier.replace("_", " ").title(),
                kinds,
                MetricScope.PAIRWISE,
                True,
                ("Nondegenerate marginals",),
                False,
                False,
                "kappa",
                "1 - observed disagreement / independent-marginal expected disagreement. "
                f"Distance: unequal-category indicator (power 0) or ordinal rank distance^{power}.",
                "1.0",
                partial(cohen, power=power),
                partial(preflight, power=power),
            )
        )
