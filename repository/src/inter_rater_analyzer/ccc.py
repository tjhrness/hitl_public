"""Pairwise Lin CCC using population (1/n) central moments."""

from inter_rater_analyzer.categorical import pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.continuous import continuous_preflight
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def ccc(data: NormalizedCriterion, settings: CriterionConfiguration) -> tuple[MetricResult, ...]:
    n = len(data.values)
    results: list[MetricResult] = []
    for a, b in pairs(data):
        left = [float(row[a]) for row in data.values]
        right = [float(row[b]) for row in data.values]
        mx, my = sum(left) / n, sum(right) / n
        vx = sum((x - mx) ** 2 for x in left) / n
        vy = sum((y - my) ** 2 for y in right) / n
        if vx <= 0 or vy <= 0:
            raise DomainError(ErrorCode.STAT_UNDEFINED, "CCC requires variation in both raters.")
        covariance = sum((x - mx) * (y - my) for x, y in zip(left, right, strict=True)) / n
        results.append(
            MetricResult(
                "lin_ccc",
                data.name,
                2 * covariance / (vx + vy + (mx - my) ** 2),
                (data.raters[a], data.raters[b]),
            )
        )
    return tuple(results)


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ValidationFinding, ...]:
    findings = continuous_preflight(data, settings)
    if findings:
        return findings
    try:
        ccc(data, settings)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_CCC_UNDEFINED", error.message, "Deselect CCC or provide variable ratings."
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    registry.register(
        MetricDefinition(
            "lin_ccc",
            "Lin's concordance correlation coefficient",
            (RatingType.CONTINUOUS,),
            MetricScope.PAIRWISE,
            True,
            ("Both raters have positive variance",),
            False,
            False,
            "ccc",
            "2*cov(x,y)/(var(x)+var(y)+(mean(x)-mean(y))^2). "
            "All moments use divisor n. Pairwise only; no panel CCC average.",
            "1.0",
            ccc,
            preflight,
        )
    )
