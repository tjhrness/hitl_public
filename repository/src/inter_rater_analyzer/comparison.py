"""Latest versus immediately preceding version, with alias-only change evidence."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from inter_rater_analyzer.domain import AnalysisVersionId, DomainError, ErrorCode, RatingType
from inter_rater_analyzer.execution import ExecutionService


@dataclass(frozen=True)
class CellChange:
    criterion: str
    item_id: str
    alias: str
    previous: str | float
    latest: str | float
    magnitude: float | None


@dataclass(frozen=True)
class ConsensusChange:
    criterion: str
    item_id: str
    previous: str | float | None
    latest: str | float | None
    material: bool


@dataclass(frozen=True)
class PriorityChange:
    item_id: str
    previous: Decimal
    latest: Decimal
    change: Decimal
    percent_change: Decimal | None


@dataclass(frozen=True)
class MetricChange:
    criterion: str
    metric_id: str
    pair: tuple[str, ...]
    previous: dict[str, Any]
    latest: dict[str, Any]


@dataclass(frozen=True)
class VersionComparison:
    cells: tuple[CellChange, ...]
    magnitudes: tuple[tuple[str, float | None], ...]
    consensus: tuple[ConsensusChange, ...]
    priorities: tuple[PriorityChange, ...]
    metrics: tuple[MetricChange, ...]
    configuration_changes: tuple[tuple[str, Any, Any], ...]
    convention: str = (
        "Ordinal changes use latest ordinal order; median materiality uses latest tolerance."
        " Ordinal distance is unavailable when a prior label is absent from the latest order."
    )


def compare_snapshots(old: dict[str, Any], new: dict[str, Any]) -> VersionComparison:
    previous_data = {d["name"]: d for d in old.get("all_data", old["data"])}
    latest_data = {d["name"]: d for d in new.get("all_data", new["data"])}
    settings = {c["name"]: c for c in new["configuration"]["criteria"]}
    cells: list[CellChange] = []
    totals: list[tuple[str, float | None]] = []
    for name, latest in latest_data.items():
        previous = previous_data[name]
        rows = dict(zip(previous["item_ids"], previous["values"], strict=True))
        ranks = {value: index for index, value in enumerate(settings[name]["ordinal_order"])}
        total: float | None = 0.0
        for item_id, row in zip(latest["item_ids"], latest["values"], strict=True):
            if item_id not in rows:
                continue
            for index, value in enumerate(row):
                before = rows[item_id][index]
                if value == before:
                    continue
                kind = RatingType(latest["rating_type"])
                magnitude = (
                    abs(float(value) - float(before))
                    if kind is RatingType.CONTINUOUS
                    else (
                        float(abs(ranks[value] - ranks[before]))
                        if value in ranks and before in ranks
                        else None
                    )
                    if kind is RatingType.ORDINAL
                    else 1.0
                )
                total = total + magnitude if total is not None and magnitude is not None else None
                cells.append(
                    CellChange(name, item_id, latest["raters"][index], before, value, magnitude)
                )
        totals.append((name, total))
    previous_results = {r["name"]: r for r in old["result"]["criteria"]}
    consensus: list[ConsensusChange] = []
    metrics: list[MetricChange] = []
    for latest in new["result"]["criteria"]:
        name = latest["name"]
        previous = previous_results[name]
        items = {i["item_id"]: i for i in previous["items"]}
        for item in latest["items"]:
            if item["item_id"] not in items:
                continue
            a, b = items[item["item_id"]]["consensus"], item["consensus"]
            if a != b:
                material = (
                    abs(float(b) - float(a)) > settings[name]["tolerance"]
                    if settings[name]["rating_type"] == RatingType.CONTINUOUS
                    else True
                )
                consensus.append(ConsensusChange(name, item["item_id"], a, b, material))
        old_metrics = {(m["metric_id"], tuple(m["pair"] or ())): m for m in previous["metrics"]}
        for metric in latest["metrics"]:
            key = (metric["metric_id"], tuple(metric["pair"] or ()))
            if key in old_metrics:
                metrics.append(MetricChange(name, key[0], key[1], old_metrics[key], metric))
    old_priority = {i["item_id"]: Decimal(i["score"]) for i in old["result"]["ranking"]}
    priorities: list[PriorityChange] = []
    for item in new["result"]["ranking"]:
        if item["item_id"] in old_priority:
            before = old_priority[item["item_id"]]
            after = Decimal(item["score"])
            delta = after - before
            priorities.append(
                PriorityChange(
                    item["item_id"], before, after, delta, delta * 100 / before if before else None
                )
            )
    changes = tuple(
        (key, old["configuration"].get(key), value)
        for key, value in new["configuration"].items()
        if old["configuration"].get(key) != value
    )
    return VersionComparison(
        tuple(cells), tuple(totals), tuple(consensus), tuple(priorities), tuple(metrics), changes
    )


@dataclass(frozen=True)
class ComparisonService:
    execution: ExecutionService

    def latest(self, identifier: AnalysisVersionId) -> VersionComparison:
        repository = self.execution.drafts.analyses
        version = repository.get_version(identifier)
        with self.execution.database.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM analysis_versions WHERE analysis_id=? ORDER BY number DESC LIMIT 2",
                (str(version.analysis_id),),
            ).fetchall()
        if len(rows) != 2 or rows[0][0] != str(identifier):
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Compare latest with immediately previous version only."
            )
        return compare_snapshots(
            self.execution.load(AnalysisVersionId.parse(rows[1][0])),
            self.execution.load(identifier),
        )
