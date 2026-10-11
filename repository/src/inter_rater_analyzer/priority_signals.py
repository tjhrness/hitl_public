"""Version 1 review-priority formulas; see docs/priority_formulas.md."""

from dataclasses import dataclass
from math import log
from statistics import mean, median

from inter_rater_analyzer.categorical import pairs
from inter_rater_analyzer.configuration import CriterionConfiguration, PrioritySignal
from inter_rater_analyzer.diagnostics import diagnose_items
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.ratings import NormalizedCriterion


@dataclass(frozen=True)
class SignalValue:
    signal: PrioritySignal
    raw: float | None
    normalized: float | None


@dataclass(frozen=True)
class ItemSignals:
    criterion: str
    item_id: str
    signals: tuple[SignalValue, ...]
    formula_version: str = "1"


def priority_signals(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ItemSignals, ...]:
    continuous = data.rating_type is RatingType.CONTINUOUS
    ordinal = data.rating_type is RatingType.ORDINAL
    ranks = {value: index for index, value in enumerate(settings.ordinal_order)}
    domain = [float(value) for row in data.values for value in row] if continuous else []
    scale = max(domain) - min(domain) if continuous else max(0, len(ranks) - 1)
    results: list[ItemSignals] = []
    for item in diagnose_items(data, settings):
        row = item.ratings
        numbers = (
            [float(ranks[v]) if ordinal else float(v) for v in row] if ordinal or continuous else []
        )
        disagreement = mean(
            (abs(numbers[a] - numbers[b]) / scale if scale else 0)
            if ordinal
            else float(abs(numbers[a] - numbers[b]) > settings.tolerance)
            if continuous
            else float(row[a] != row[b])
            for a, b in pairs(data)
        )
        inverse = None if continuous else 1 - float(item.modal_share or 0)
        if ordinal or continuous:
            spread = (max(numbers) - min(numbers)) / scale if scale else 0
            center = (
                float(ranks[item.consensus])
                if ordinal and item.consensus is not None
                else median(numbers)
            )
            deviation: float | None = (
                mean(abs(value - center) for value in numbers) / scale if scale else 0
            )
        else:
            entropy = -sum(
                (count / len(row)) * log(count / len(row)) for _, count in item.frequencies
            )
            spread = entropy / log(len(data.categories)) if len(data.categories) > 1 else 0
            deviation = None
        raw = (
            disagreement,
            inverse,
            spread,
            deviation,
            float(any(item.outliers)),
            None if continuous else float(item.consensus is None),
        )
        results.append(
            ItemSignals(
                data.name,
                item.item_id,
                tuple(
                    SignalValue(
                        signal, value, None if value is None else min(100.0, max(0.0, 100 * value))
                    )
                    for signal, value in zip(PrioritySignal, raw, strict=True)
                ),
            )
        )
    return tuple(results)
