"""Validated unweighted Cohen null test; Holm within criterion/test family."""

import math
from collections import Counter
from dataclasses import replace

from inter_rater_analyzer.metric_registry import MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def holm(values: tuple[float, ...]) -> tuple[float, ...]:
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
        raise ValueError("P-values must be finite probabilities.")
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    adjusted = [0.0] * len(values)
    previous = 0.0
    for rank, index in enumerate(ordered):
        previous = min(1.0, max(previous, (len(values) - rank) * values[index]))
        adjusted[index] = previous
    return tuple(adjusted)


def add_significance(
    results: tuple[MetricResult, ...], data: NormalizedCriterion
) -> tuple[MetricResult, ...]:
    updated = list(results)
    families: dict[tuple[str, str], list[tuple[int, float]]] = {}
    n = len(data.values)
    for index, result in enumerate(results):
        if (
            result.metric_id != "cohen_kappa"
            or result.pair is None
            or result.criterion != data.name
        ):
            continue
        a, b = (data.raters.index(alias) for alias in result.pair)
        left, right = Counter(row[a] for row in data.values), Counter(row[b] for row in data.values)
        marginals = [(left[c] / n, right[c] / n) for c in data.categories]
        expected = sum(p * q for p, q in marginals)
        variance = (
            (
                (expected + expected**2 - sum(p * q * (p + q) for p, q in marginals))
                / ((1 - expected) ** 2 * n)
            )
            if expected < 1
            else 0
        )
        if variance <= 0:
            updated[index] = replace(
                result,
                warnings=result.warnings
                + ("Significance unavailable: null variance is nonpositive.",),
            )
            continue
        internal_p = math.erfc(abs(result.estimate) / math.sqrt(2 * variance))
        families.setdefault((result.criterion, result.metric_id), []).append((index, internal_p))
    for members in families.values():
        corrected = holm(tuple(p for _, p in members))
        for (index, _), adjusted in zip(members, corrected, strict=True):
            updated[index] = replace(
                updated[index],
                adjusted_p=adjusted,
                warnings=updated[index].warnings
                + ("Two-sided asymptotic kappa=0 test; Holm adjusted.",),
            )
    return tuple(updated)
