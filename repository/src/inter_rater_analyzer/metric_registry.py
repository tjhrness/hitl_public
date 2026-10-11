"""Metric metadata, public finite results, and actual implementation registry."""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import TYPE_CHECKING

from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating

if TYPE_CHECKING:
    from inter_rater_analyzer.configuration import CriterionConfiguration


@dataclass(frozen=True)
class ConfidenceInterval:
    lower: float
    upper: float
    confidence: float
    method: str

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.lower, self.upper, self.confidence)):
            raise ValueError("Confidence interval must be finite.")
        if self.lower > self.upper or not 0 < self.confidence < 100 or not self.method:
            raise ValueError("Invalid confidence interval.")


@dataclass(frozen=True)
class ConfusionMatrix:
    categories: tuple[Rating, ...]
    counts: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class BlandAltmanData:
    item_ids: tuple[str, ...]
    means: tuple[float, ...]
    differences: tuple[float, ...]
    sd: float
    lower: float
    upper: float


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    criterion: str
    estimate: float
    pair: tuple[str, str] | None = None
    ci: ConfidenceInterval | None = None
    adjusted_p: float | None = None
    interpretation: str = ""
    convention: str = ""
    warnings: tuple[str, ...] = ()
    implementation_version: str = "1.0"
    confusion: ConfusionMatrix | None = None
    components: tuple[tuple[str, float], ...] = ()
    bland_altman: BlandAltmanData | None = None
    bootstrap_resamples: int | None = None
    bootstrap_seed: int | None = None
    bootstrap_seed_scheme: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.estimate):
            raise ValueError("Metric estimate must be finite.")
        if self.adjusted_p is not None and not 0 <= self.adjusted_p <= 1:
            raise ValueError("Adjusted p-value must be in [0,1].")


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    name: str
    rating_types: tuple[RatingType, ...]
    scope: MetricScope
    recommended: bool
    prerequisites: tuple[str, ...]
    ci_capable: bool
    significance_capable: bool
    interpretation_key: str
    methodology: str
    implementation_version: str
    calculate: Callable[[NormalizedCriterion, CriterionConfiguration], tuple[MetricResult, ...]]
    preflight: Callable[
        [NormalizedCriterion, CriterionConfiguration], tuple[ValidationFinding, ...]
    ]


class MetricRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> None:
        if definition.id in self._definitions:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Metric ID is already registered.")
        self._definitions[definition.id] = definition

    def enable_confidence_intervals(self) -> None:
        for identifier, definition in self._definitions.items():
            self._definitions[identifier] = replace(
                definition, ci_capable=True, significance_capable=identifier == "cohen_kappa"
            )

    def get(self, identifier: str) -> MetricDefinition:
        try:
            return self._definitions[identifier]
        except KeyError as error:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Selected metric is unavailable."
            ) from error

    def applicable(self, kind: RatingType) -> tuple[MetricDefinition, ...]:
        return tuple(d for _, d in sorted(self._definitions.items()) if kind in d.rating_types)

    def defaults(self, kind: RatingType) -> tuple[str, ...]:
        return tuple(d.id for d in self.applicable(kind) if d.recommended)

    def validate_selection(self, identifiers: tuple[str, ...], kind: RatingType) -> None:
        if len(set(identifiers)) != len(identifiers):
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Choose each metric only once.")
        for identifier in identifiers:
            if kind not in self.get(identifier).rating_types:
                raise DomainError(
                    ErrorCode.VALIDATION_VALUE, "Metric is unsuitable for rating type."
                )


@lru_cache(maxsize=1)
def get_registry() -> MetricRegistry:
    from inter_rater_analyzer.alpha import register_metrics as register_alpha
    from inter_rater_analyzer.bland_altman import register_metrics as register_bland_altman
    from inter_rater_analyzer.categorical import register_metrics
    from inter_rater_analyzer.ccc import register_metrics as register_ccc
    from inter_rater_analyzer.continuous import register_metrics as register_continuous
    from inter_rater_analyzer.fleiss import register_metrics as register_fleiss
    from inter_rater_analyzer.gwet import register_metrics as register_gwet
    from inter_rater_analyzer.icc import register_metrics as register_icc
    from inter_rater_analyzer.kappa import register_metrics as register_kappa

    registry = MetricRegistry()
    register_metrics(registry)
    register_kappa(registry)
    register_fleiss(registry)
    register_alpha(registry)
    register_gwet(registry)
    register_continuous(registry)
    register_ccc(registry)
    register_icc(registry)
    register_bland_altman(registry)
    registry.enable_confidence_intervals()
    return registry
