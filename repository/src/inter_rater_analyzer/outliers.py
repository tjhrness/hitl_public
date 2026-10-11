"""Fixed, deterministic item outlier rules from the project contract."""

from collections import Counter
from statistics import median

from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.ratings import Rating


def outlier_flags(
    row: tuple[Rating, ...],
    kind: RatingType,
    *,
    order: tuple[Rating, ...] = (),
    tolerance: float = 0.0,
) -> tuple[bool, ...]:
    if len(row) < 3:
        return tuple(False for _ in row)
    if kind in (RatingType.BINARY, RatingType.NOMINAL):
        counts = Counter(row)
        return tuple(
            len(counts) == 2 and counts[value] == 1 and max(counts.values()) == len(row) - 1
            for value in row
        )
    if kind is RatingType.ORDINAL:
        ranks = {value: index for index, value in enumerate(order)}
        values = tuple(float(ranks[value]) for value in row)
        center = median(values)
        return tuple(
            abs(value - center) >= 2
            and all(abs(other - center) <= 1 for j, other in enumerate(values) if j != i)
            for i, value in enumerate(values)
        )
    values = tuple(float(value) for value in row)
    center = median(values)
    mad = median(abs(value - center) for value in values)
    if mad > 0:
        return tuple(abs(0.6745 * (value - center) / mad) > 3.5 for value in values)
    return tuple(
        len(set(values[:i] + values[i + 1 :])) == 1 and abs(value - center) > tolerance
        for i, value in enumerate(values)
    )
