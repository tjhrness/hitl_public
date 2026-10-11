"""Fixed complete-panel Fleiss kappa with pooled empirical category marginals."""

from collections import Counter

from inter_rater_analyzer.categorical import complete_preflight, raw_agreement
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def fleiss(data: NormalizedCriterion, settings: CriterionConfiguration) -> tuple[MetricResult, ...]:
    counts = Counter(value for row in data.values for value in row)
    total = counts.total()
    expected = sum((count / total) ** 2 for count in counts.values())
    if expected >= 1:
        raise DomainError(ErrorCode.STAT_UNDEFINED, "Fleiss kappa requires category variation.")
    observed = raw_agreement(data, settings)[0].estimate / 100
    return (MetricResult("fleiss_kappa", data.name, (observed - expected) / (1 - expected)),)


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ValidationFinding, ...]:
    findings = complete_preflight(data, settings)
    if findings:
        return findings
    try:
        fleiss(data, settings)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_FLEISS_UNDEFINED",
                error.message,
                "Deselect Fleiss kappa or provide category variation.",
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    registry.register(
        MetricDefinition(
            "fleiss_kappa",
            "Fleiss kappa",
            (RatingType.BINARY, RatingType.NOMINAL),
            MetricScope.OVERALL,
            True,
            ("Complete fixed panel", "Pooled category variation"),
            False,
            False,
            "kappa",
            "(P_observed - sum(p_category^2)) / (1 - sum(p_category^2)); "
            "P_observed averages agreement over every item and unordered rater pair.",
            "1.0",
            fleiss,
            preflight,
        )
    )
