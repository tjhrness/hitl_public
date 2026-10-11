"""Deterministic descriptive summary rules; all triggers expose their evidence."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.priority import ItemPriority
from inter_rater_analyzer.ratings import NormalizedCriterion

if TYPE_CHECKING:
    from inter_rater_analyzer.analytics import CriterionResult


@dataclass(frozen=True)
class SummaryEntry:
    rule_id: str
    severity: str
    message: str
    why: str
    criterion: str | None = None


def executive_summary(
    results: tuple[CriterionResult, ...],
    data: tuple[NormalizedCriterion, ...],
    ranking: tuple[ItemPriority, ...],
) -> tuple[SummaryEntry, ...]:
    entries: list[SummaryEntry] = []
    source = {criterion.name: criterion for criterion in data}
    for result in results:
        current = source.get(result.name)
        if current is not None:
            for warning in quality_warnings(current):
                entries.append(
                    SummaryEntry(
                        warning.code, "warning", warning.message, warning.message, result.name
                    )
                )
        for metric in result.metrics:
            key = get_registry().get(metric.metric_id).interpretation_key
            threshold = (
                0.4
                if key == "kappa"
                else 0.667
                if key == "alpha"
                else 0.5
                if key == "icc"
                else None
            )
            if threshold is not None and (
                metric.estimate <= threshold if key == "kappa" else metric.estimate < threshold
            ):
                entries.append(
                    SummaryEntry(
                        "CONCERNING_AGREEMENT",
                        "warning",
                        f"{metric.metric_id}: {metric.interpretation}.",
                        f"Estimate={metric.estimate:g}; concern threshold "
                        f"{'<=' if key == 'kappa' else '<'}{threshold:g}; "
                        f"pair={metric.pair}; {metric.convention}",
                        result.name,
                    )
                )
            for warning in metric.warnings:
                rule = "KAPPA_PREVALENCE" if "prevalence" in warning else "METRIC_SUITABILITY"
                entries.append(
                    SummaryEntry(
                        rule,
                        "warning",
                        warning,
                        f"{metric.metric_id}; pair={metric.pair}; {warning}",
                        result.name,
                    )
                )
        tied = sum(item.consensus is None for item in result.items)
        if tied:
            n = len(result.items)
            entries.append(
                SummaryEntry(
                    "NO_CONSENSUS",
                    "warning",
                    "Some items have no unique categorical consensus.",
                    f"{tied}/{n} items ({100 * tied / n:g}%) have tied modes; trigger: count > 0.",
                    result.name,
                )
            )
        for rater in result.raters:
            if rater.direction is not None and rater.direction != 0:
                entries.append(
                    SummaryEntry(
                        "ORDERED_DIRECTION",
                        "information",
                        f"{rater.alias} scores {'higher' if rater.direction > 0 else 'lower'} "
                        "than the item panel median on average.",
                        f"Mean signed deviation={rater.direction:g}; trigger: nonzero mean; "
                        "rank steps for ordinal, original units for continuous. "
                        "Descriptive tendency, not a causal or significance claim.",
                        result.name,
                    )
                )
            # A 20 percentage-point gap is a workflow review threshold, not a hypothesis test.
            peer_mean = sum(r.disagreement for r in result.raters) / len(result.raters)
            gap = rater.disagreement - peer_mean
            if gap >= 20:
                direction = (
                    ""
                    if rater.direction is None
                    else f" Mean signed panel-median deviation={rater.direction:g}."
                )
                entries.append(
                    SummaryEntry(
                        "RATER_DIVERGENCE",
                        "warning",
                        f"{rater.alias} has elevated disagreement with peers.",
                        f"Disagreement={rater.disagreement:g}%; panel mean={peer_mean:g}%; "
                        f"gap={gap:g} percentage points >=20.{direction}",
                        result.name,
                    )
                )
    # Compare only exact overall agreement percentages, same type and included item cohort.
    comparable = [
        (result, metric, source[result.name])
        for result in results
        if result.name in source
        for metric in result.metrics
        if metric.metric_id == "raw_agreement" and metric.pair is None
    ]
    for index, (left, a, left_data) in enumerate(comparable):
        for right, b, right_data in comparable[index + 1 :]:
            if (left_data.rating_type, left_data.item_ids, left_data.raters) != (
                right_data.rating_type,
                right_data.item_ids,
                right_data.raters,
            ):
                continue
            if a.estimate != b.estimate:
                high, low = (
                    (left.name, right.name) if a.estimate > b.estimate else (right.name, left.name)
                )
                entries.append(
                    SummaryEntry(
                        "CRITERION_COMPARISON",
                        "information",
                        f"{high} has higher observed exact agreement than {low}.",
                        f"Same rating type, item cohort and panel; raw_agreement: "
                        f"{left.name}={a.estimate:g}%, {right.name}={b.estimate:g}%; "
                        "descriptive comparison, not a significance claim.",
                    )
                )
    if ranking:
        top = ranking[0]
        entries.append(
            SummaryEntry(
                "HIGHEST_PRIORITY",
                "information",
                f"Review Item ID {top.item_id} first.",
                f"Rank={top.rank}; score={top.score}; descending score, "
                "case-sensitive Item ID tie-break.",
            )
        )
    return tuple(entries)
