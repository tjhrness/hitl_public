"""Headless selected-metric execution with mandatory suitability checks."""

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.metric_registry import MetricResult, get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion


def execute_metrics(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
) -> tuple[MetricResult, ...]:
    registry = get_registry()
    registry.validate_selection(settings.metrics, data.rating_type)
    definitions = tuple(registry.get(identifier) for identifier in settings.metrics)
    for definition in definitions:
        findings = definition.preflight(data, settings)
        if findings:
            raise DomainError(ErrorCode.STAT_UNDEFINED, findings[0].message)
    return tuple(
        result for definition in definitions for result in definition.calculate(data, settings)
    )
