"""Release benchmark: no reduced resample count or skipped recommended metrics."""

import json
import platform
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from openpyxl import Workbook

from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating
from inter_rater_analyzer.services import Services


def maximum_fixture() -> tuple[tuple[NormalizedCriterion, ...], AnalysisConfiguration]:
    rng = np.random.default_rng(1729)
    criteria: list[NormalizedCriterion] = []
    settings: list[CriterionConfiguration] = []
    kinds = (RatingType.BINARY, RatingType.NOMINAL, RatingType.ORDINAL, RatingType.CONTINUOUS)
    for index in range(10):
        kind = kinds[index % 4]
        rows: tuple[tuple[Rating, ...], ...]
        categories: tuple[Rating, ...]
        if kind is RatingType.CONTINUOUS:
            values = rng.normal(50, 10, (1000, 1)) + rng.normal(0, 4, (1000, 10))
            rows = tuple(tuple(float(v) for v in row) for row in values)
            categories = ()
        else:
            q = 2 if kind is RatingType.BINARY else 5
            values = rng.integers(0, q, (1000, 10))
            rows = tuple(tuple(f"level {v}" for v in row) for row in values)
            categories = tuple(f"level {v}" for v in range(q))
        name = f"Criterion {index + 1}"
        criteria.append(
            NormalizedCriterion(
                name,
                kind,
                tuple(f"I{i:04}" for i in range(1000)),
                tuple(f"Rater {chr(65 + i)}" for i in range(10)),
                rows,
                categories,
                None,
                None,
            )
        )
        settings.append(
            CriterionConfiguration(
                name,
                kind,
                ordinal_order=categories if kind is RatingType.ORDINAL else (),
                tolerance=3.0,
                metrics=get_registry().defaults(kind),
            )
        )
    return tuple(criteria), AnalysisConfiguration(tuple(settings))


def main() -> int:
    data, config = maximum_fixture()
    Path("runtime-data").mkdir(exist_ok=True)
    with TemporaryDirectory(dir="runtime-data") as temporary:
        root = Path(temporary)
        book = Workbook()
        book.remove(book.active)  # type: ignore[arg-type]
        for criterion in data:
            sheet = book.create_sheet(criterion.name)
            sheet.append(["Item ID", *(f"Rater:Person{i}" for i in range(10))])
            for item, row in zip(criterion.item_ids, criterion.values, strict=True):
                sheet.append([item, *row])
        source = root / "maximum.xlsx"
        book.save(source)
        book.close()
        services = Services.open(root / "state")
        services.drafts.create("Maximum release benchmark")
        services.drafts.attach_workbook(source)
        state = services.drafts.active()
        assert state is not None
        services.drafts.save(
            replace(
                state,
                configuration=config,
                types_locked=True,
                acknowledged_warnings=(
                    "WARNING_SAMPLE_SIZE",
                    "WARNING_IMBALANCE",
                    "WARNING_SEVERE_IMBALANCE",
                    "WARNING_HIGH_CARDINALITY",
                ),
            )
        )
        start = perf_counter()
        result = services.execution.execute(state.version_id, worker_processes=True)
        seconds = perf_counter() - start
    record = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "seconds": seconds,
        "limit_seconds": 60,
        "passed": seconds <= 60,
        "criteria": 10,
        "items": 1000,
        "raters": 10,
        "resamples": 10000,
        "metric_results": sum(len(c.metrics) for c in result.criteria),
        "timing_boundary": "Execute including workbook reload, validation, preflight, "
        "computation and persistence; excludes initial upload",
        "selected": {c.name: c.metrics for c in config.criteria},
    }
    path = Path("runtime-data/benchmark.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0 if seconds <= 60 else 1


if __name__ == "__main__":
    raise SystemExit(main())
