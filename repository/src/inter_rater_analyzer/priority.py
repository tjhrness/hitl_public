"""Decimal-safe priority composition with a complete contribution ledger."""

from dataclasses import dataclass, replace
from decimal import Decimal

from inter_rater_analyzer.configuration import PrioritySignal, SignalWeight
from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.priority_signals import ItemSignals


@dataclass(frozen=True)
class Contribution:
    signal: PrioritySignal
    raw: float | None
    normalized: float | None
    configured_weight: Decimal
    effective_weight: Decimal
    contribution: Decimal


@dataclass(frozen=True)
class CriterionPriority:
    criterion: str
    score: Decimal
    contributions: tuple[Contribution, ...]


@dataclass(frozen=True)
class ItemPriority:
    item_id: str
    rank: int
    score: Decimal
    criteria: tuple[CriterionPriority, ...]


def rank_items(
    criteria: tuple[tuple[ItemSignals, ...], ...], weights: tuple[SignalWeight, ...]
) -> tuple[ItemPriority, ...]:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise DomainError(ErrorCode.VALIDATION_VALUE, message)

    require(bool(weights), "Select priority signals.")
    require(
        all(w.weight.is_finite() and w.weight >= 0 for w in weights),
        "Priority weights must be finite and nonnegative.",
    )
    require(sum(w.weight for w in weights) == 100, "Priority weights must total 100%.")
    require(len({w.signal for w in weights}) == len(weights), "Duplicate priority signal.")
    require(bool(criteria) and all(criteria), "Priority requires included items.")
    maps = [{item.item_id: item for item in criterion} for criterion in criteria]
    require(
        all(set(mapping) == set(maps[0]) for mapping in maps),
        "Priority criteria must have matching Item IDs.",
    )
    results: list[ItemPriority] = []
    for item_id in sorted(maps[0]):
        scores: list[CriterionPriority] = []
        for mapping in maps:
            item = mapping[item_id]
            signals = {s.signal: s for s in item.signals}
            require(all(w.signal in signals for w in weights), "Missing selected priority signal.")
            active = [
                w for w in weights if signals[w.signal].normalized is not None and w.weight > 0
            ]
            total = sum((w.weight for w in active), Decimal(0))
            require(total > 0, "No positively weighted priority signal applies to this criterion.")
            effective = {w.signal: w.weight * 100 / total for w in active}
            # Preserve an exact 100 total after finite Decimal division.
            effective[active[-1].signal] += Decimal(100) - sum(effective.values())
            contributions: list[Contribution] = []
            for weight in weights:
                signal = signals[weight.signal]
                value = signal.normalized
                require(value is None or 0 <= value <= 100, "Priority signal outside [0,100].")
                percent = effective.get(weight.signal, Decimal(0))
                contributions.append(
                    Contribution(
                        weight.signal,
                        signal.raw,
                        value,
                        weight.weight,
                        percent,
                        percent * Decimal(str(value or 0)) / 100,
                    )
                )
            scores.append(
                CriterionPriority(
                    item.criterion,
                    sum((c.contribution for c in contributions), Decimal(0)),
                    tuple(contributions),
                )
            )
        results.append(
            ItemPriority(
                item_id, 0, sum((s.score for s in scores), Decimal(0)) / len(scores), tuple(scores)
            )
        )
    return tuple(
        replace(result, rank=index + 1)
        for index, result in enumerate(
            sorted(results, key=lambda result: (-result.score, result.item_id))
        )
    )
