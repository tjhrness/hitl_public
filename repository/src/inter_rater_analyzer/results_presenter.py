"""Read-only dashboard projections and help derived from persisted evidence."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from inter_rater_analyzer.domain import AnalysisVersionId, DomainError, RatingType
from inter_rater_analyzer.services import Services


@dataclass(frozen=True)
class ResultsPresenter:
    services: Services
    identifier: AnalysisVersionId

    def snapshot(self) -> dict[str, Any]:
        return self.services.execution.load(self.identifier)

    def help_text(self) -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        for criterion in snapshot["result"]["criteria"]:
            for metric in criterion["metrics"]:
                metadata = self.services.metrics.get(metric["metric_id"])
                lines += [f"{metadata.name}: {metadata.methodology}", metric["convention"]]
        lines += [entry["why"] for entry in snapshot["result"]["summary"]]
        lines += [
            "Pairwise heatmap: exact categorical or within-tolerance continuous agreement (%).",
            "Item heatmap: saved normalized priority signals; 0 is lowest, 100 is highest.",
            "Priority: equal mean of criterion scores; "
            "expand an item to inspect effective weights.",
            "N/A means the quantity does not apply or cannot be compared defensibly.",
        ]
        return "\n\n".join(lines)

    def pairwise(self, name: str) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]:
        snapshot = self.snapshot()
        data = next(d for d in snapshot["data"] if d["name"] == name)
        settings = next(c for c in snapshot["configuration"]["criteria"] if c["name"] == name)
        aliases = tuple(data["raters"])
        rows: list[tuple[object, ...]] = []
        for a, alias in enumerate(aliases):
            values: list[object] = [alias]
            for b in range(len(aliases)):
                agreed = sum(
                    abs(float(row[a]) - float(row[b])) <= settings["tolerance"]
                    if data["rating_type"] == RatingType.CONTINUOUS
                    else row[a] == row[b]
                    for row in data["values"]
                )
                values.append(100 * agreed / len(data["values"]))
            rows.append(tuple(values))
        return ("Rater", *aliases), tuple(rows)

    def item_text(self, item_id: str) -> str:
        snapshot = self.snapshot()
        priority = next(p for p in snapshot["result"]["ranking"] if p["item_id"] == item_id)
        lines = [f"Item ID {item_id}", f"Workbook priority: {priority['score']}"]
        for criterion in snapshot["result"]["criteria"]:
            item = next(i for i in criterion["items"] if i["item_id"] == item_id)
            score = next(c for c in priority["criteria"] if c["criterion"] == criterion["name"])
            lines += [
                "",
                criterion["name"],
                "Consensus: "
                + str(item["consensus"] if item["consensus"] is not None else "No consensus"),
            ]
            lines += [
                f"{alias}: {rating}; outlier: {flag}"
                for alias, rating, flag in zip(
                    item["raters"], item["ratings"], item["outliers"], strict=True
                )
            ]
            lines += [
                f"Criterion score: {score['score']}",
                f"Workbook contribution: {Decimal(score['score']) / len(priority['criteria'])}",
            ]
            for c in score["contributions"]:
                lines.append(
                    f"{c['signal']}: normalized={c['normalized']}; "
                    f"configured weight={c['configured_weight']}%; "
                    f"effective={c['effective_weight']}%; "
                    f"contribution={c['contribution']}"
                )
        return "\n".join(lines)

    def comparison_text(self) -> str | None:
        try:
            comparison = self.services.comparisons.latest(self.identifier)
        except DomainError:
            return None
        lines = [comparison.convention, f"Changed rating cells: {len(comparison.cells)}"]
        lines += [f"{name}: change magnitude {value}" for name, value in comparison.magnitudes]
        lines += [
            f"{c.criterion} / {c.item_id} / {c.alias}: {c.previous} → {c.latest}"
            for c in comparison.cells
        ]
        lines += [
            f"{c.criterion} / {c.item_id}: consensus {c.previous} → {c.latest}; "
            f"material={c.material}"
            for c in comparison.consensus
        ]
        lines += [
            f"{p.item_id}: priority {p.previous} → {p.latest}; change={p.change}; "
            f"percent={p.percent_change if p.percent_change is not None else 'N/A'}"
            for p in comparison.priorities
        ]
        lines += [
            f"{m.criterion} / {m.metric_id} / {m.pair}: "
            f"{m.previous['estimate']} → {m.latest['estimate']}; "
            f"CI {m.previous['ci']} → {m.latest['ci']}; "
            f"{m.previous['interpretation']} → {m.latest['interpretation']}"
            for m in comparison.metrics
        ]
        lines += [
            f"{key}: {before} → {after}" for key, before, after in comparison.configuration_changes
        ]
        return "\n".join(lines)
