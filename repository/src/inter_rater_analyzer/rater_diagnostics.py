"""Descriptive rater diagnostics in alias order; percentages use all item-peer pairs."""

from dataclasses import dataclass
from statistics import mean, median, pvariance

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.diagnostics import diagnose_items
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating


@dataclass(frozen=True)
class RaterDiagnostic:
    alias: str
    agreement: float
    disagreement: float
    outlier_frequency: float
    distribution: tuple[tuple[Rating, float], ...]
    variance: float | None
    spread: float | None
    direction: float | None


def diagnose_raters(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[RaterDiagnostic, ...]:
    items = diagnose_items(data, settings)
    ordinal = data.rating_type is RatingType.ORDINAL
    continuous = data.rating_type is RatingType.CONTINUOUS
    ordered = ordinal or continuous
    ranks = {value: index for index, value in enumerate(settings.ordinal_order)}

    def number(value: Rating) -> float:
        return float(ranks[value]) if ordinal else float(value)

    results: list[RaterDiagnostic] = []
    for index, alias in enumerate(data.raters):
        column = [row[index] for row in data.values]
        agreements: list[float] = []
        disagreements: list[float] = []
        directions: list[float] = []
        for row in data.values:
            if ordered:
                directions.append(number(row[index]) - median(map(number, row)))
            for peer in range(len(row)):
                if peer == index:
                    continue
                distance = abs(number(row[index]) - number(row[peer])) if ordered else 0.0
                agreement = (
                    distance <= settings.tolerance if continuous else row[index] == row[peer]
                )
                agreements.append(float(agreement))
                disagreements.append(
                    distance / max(1, len(ranks) - 1) if ordinal else float(not agreement)
                )
        numeric = list(map(number, column)) if ordered else []
        results.append(
            RaterDiagnostic(
                alias,
                100 * mean(agreements),
                100 * mean(disagreements),
                100 * mean(float(item.outliers[index]) for item in items),
                tuple(
                    (category, column.count(category) / len(column)) for category in data.categories
                )
                if not continuous
                else (),
                pvariance(numeric) if ordered else None,
                max(numeric) - min(numeric) if ordered else None,
                mean(directions) if ordered else None,
            )
        )
    return tuple(results)
