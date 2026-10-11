"""Anonymized per-item consensus and disagreement inputs."""

from collections import Counter
from dataclasses import dataclass
from statistics import median

from inter_rater_analyzer.categorical import pairs
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.outliers import outlier_flags
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating, category_key


@dataclass(frozen=True)
class ItemDiagnostic:
    criterion: str
    item_id: str
    raters: tuple[str, ...]
    ratings: tuple[Rating, ...]
    consensus: Rating | None
    modal_share: float | None
    frequencies: tuple[tuple[Rating, int], ...]
    near_agreement: float | None = None
    outliers: tuple[bool, ...] = ()

    @property
    def consensus_label(self) -> str:
        return str(self.consensus) if self.consensus is not None else "No consensus"

    @property
    def outlier_signal(self) -> float:
        return 100.0 if any(self.outliers) else 0.0


def diagnose_items(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ItemDiagnostic, ...]:
    results: list[ItemDiagnostic] = []
    ranks = {category: index for index, category in enumerate(settings.ordinal_order)}
    for item_id, row in zip(data.item_ids, data.values, strict=True):
        counts = Counter(row)
        frequencies = tuple(sorted(counts.items(), key=lambda entry: category_key(entry[0])))
        share: float | None = None
        near: float | None = None
        if data.rating_type is RatingType.CONTINUOUS:
            consensus = float(median(float(value) for value in row))
        else:
            largest = max(counts.values())
            modes = [category for category, count in counts.items() if count == largest]
            consensus = modes[0] if len(modes) == 1 else None
            share = largest / len(row)
            if data.rating_type is RatingType.ORDINAL:
                near = (
                    100
                    * sum(abs(ranks[row[a]] - ranks[row[b]]) <= 1 for a, b in pairs(data))
                    / len(pairs(data))
                )
        results.append(
            ItemDiagnostic(
                data.name,
                item_id,
                data.raters,
                row,
                consensus,
                share,
                frequencies,
                near,
                outlier_flags(
                    row,
                    data.rating_type,
                    order=settings.ordinal_order,
                    tolerance=settings.tolerance,
                ),
            )
        )
    return tuple(results)
