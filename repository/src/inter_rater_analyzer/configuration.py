"""Validated immutable execution configuration; Decimal-safe selected weights."""

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from inter_rater_analyzer.domain import DomainError, ErrorCode, RatingType, ValidationSeverity
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating


class PrioritySignal(StrEnum):
    PAIRWISE = "pairwise_disagreement"
    INVERSE_CONSENSUS = "inverse_consensus"
    SPREAD = "spread_entropy"
    DEVIATION = "deviation"
    OUTLIER = "outlier"
    NO_CONSENSUS = "no_consensus"


@dataclass(frozen=True)
class SignalWeight:
    signal: PrioritySignal
    weight: Decimal


DEFAULT_WEIGHTS = tuple(
    SignalWeight(signal, Decimal(weight))
    for signal, weight in (
        (PrioritySignal.PAIRWISE, 35),
        (PrioritySignal.INVERSE_CONSENSUS, 25),
        (PrioritySignal.SPREAD, 20),
        (PrioritySignal.DEVIATION, 15),
        (PrioritySignal.OUTLIER, 5),
    )
)


@dataclass(frozen=True)
class Exclusion:
    item_id: str
    reason: str


@dataclass(frozen=True)
class CriterionConfiguration:
    name: str
    rating_type: RatingType
    ordinal_order: tuple[Rating, ...] = ()
    tolerance: float = 0.0
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisConfiguration:
    criteria: tuple[CriterionConfiguration, ...]
    confidence: float = 95.0
    alpha: float = 0.05
    exclusions: tuple[Exclusion, ...] = ()
    weights: tuple[SignalWeight, ...] = DEFAULT_WEIGHTS


def recommended_tolerance(data: NormalizedCriterion) -> float:
    if data.minimum is None or data.maximum is None:
        return 0.0
    return 0.05 * (data.maximum - data.minimum)


def validate_configuration(
    config: AnalysisConfiguration, data: tuple[NormalizedCriterion, ...]
) -> AnalysisConfiguration:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise DomainError(ErrorCode.VALIDATION_VALUE, message)

    require(
        math.isfinite(config.confidence) and 0 < config.confidence < 100,
        "Confidence must be between 0 and 100, exclusive.",
    )
    require(
        math.isfinite(config.alpha) and 0 < config.alpha < 1,
        "Alpha must be between 0 and 1, exclusive.",
    )
    require(bool(data), "Add at least one criterion.")
    require(
        len(config.criteria) == len(data)
        and {c.name for c in config.criteria} == {d.name for d in data},
        "Configure every criterion exactly once.",
    )
    require(
        all(f.severity is not ValidationSeverity.ERROR for d in data for f in d.findings),
        "Resolve blocking rating findings first.",
    )
    require(
        bool(config.weights) and len({w.signal for w in config.weights}) == len(config.weights),
        "Select unique priority signals.",
    )
    require(
        all(w.weight.is_finite() and w.weight >= 0 for w in config.weights),
        "Weights must be finite and nonnegative.",
    )
    require(
        sum((w.weight for w in config.weights), Decimal(0)) == Decimal(100),
        "Selected weights must total exactly 100%.",
    )
    excluded = {exclusion.item_id for exclusion in config.exclusions}
    require(len(excluded) == len(config.exclusions), "Exclude each Item ID only once.")
    require(
        all(exclusion.reason.strip() for exclusion in config.exclusions),
        "Enter a reason for every exclusion.",
    )
    for current in data:
        require(excluded <= set(current.item_ids), "Excluded Item ID does not exist.")
        require(bool(set(current.item_ids) - excluded), "Keep at least one included Item ID.")
    for settings in config.criteria:
        get_registry().validate_selection(settings.metrics, settings.rating_type)
        current = next(d for d in data if d.name == settings.name)
        require(settings.rating_type is current.rating_type, "Rating types must match.")
        require(
            math.isfinite(settings.tolerance) and settings.tolerance >= 0,
            "Tolerance must be finite and nonnegative.",
        )
        if settings.rating_type is RatingType.ORDINAL:
            require(
                len(settings.ordinal_order) == len(current.categories)
                and set(settings.ordinal_order) == set(current.categories),
                "Ordinal order must contain every normalized category exactly once.",
            )
        require(
            len(set(settings.metrics)) == len(settings.metrics), "Choose each metric only once."
        )
    return config
