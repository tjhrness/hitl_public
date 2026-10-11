from dataclasses import replace

import numpy as np
import pytest

from inter_rater_analyzer.bootstrap import bca_bootstrap
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.fast_statistics import prepare_statistic
from inter_rater_analyzer.metric_execution import execute_metrics
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion


@pytest.mark.parametrize("kind", list(RatingType))
def test_vectorized_statistics_match_reference_for_resamples_and_jackknife(kind):
    rng = np.random.default_rng(49)
    values = (
        rng.normal(size=(40, 4))
        if kind is RatingType.CONTINUOUS
        else rng.integers(0, 2 if kind is RatingType.BINARY else 4, size=(40, 4))
    )
    rows = tuple(
        tuple(float(v) if kind is RatingType.CONTINUOUS else str(v) for v in row) for row in values
    )
    categories = (
        () if kind is RatingType.CONTINUOUS else tuple(sorted({v for row in rows for v in row}))
    )
    data = NormalizedCriterion(
        "Example",
        kind,
        tuple(map(str, range(40))),
        ("Rater A", "Rater B", "Rater C", "Rater D"),
        rows,
        categories,
        None,
        None,
        (),
    )
    settings = CriterionConfiguration(
        "Example",
        kind,
        ordinal_order=categories if kind is RatingType.ORDINAL else (),
        tolerance=0.5,
        metrics=tuple(m.id for m in get_registry().applicable(kind)),
    )
    for target in execute_metrics(data, settings):
        fast = prepare_statistic(data, settings, target)
        samples = rng.integers(0, 40, size=(5, 40))
        observed = fast.batch(samples.astype(float))
        for index, sample in enumerate(samples):
            subset = replace(data, values=tuple(rows[i] for i in sample))
            expected = next(
                r.estimate
                for r in get_registry().get(target.metric_id).calculate(subset, settings)
                if r.pair == target.pair
            )
            assert observed[index] == pytest.approx(expected, abs=1e-10)
        expected_jack = next(
            r.estimate
            for r in get_registry()
            .get(target.metric_id)
            .calculate(replace(data, values=rows[1:]), settings)
            if r.pair == target.pair
        )
        assert fast.jackknife()[0] == pytest.approx(expected_jack, abs=1e-10)
        if target.pair is None or target.pair == ("Rater A", "Rater B"):
            indices = np.arange(40, dtype=float)
            serial = bca_bootstrap(
                indices, fast, keys=("equivalence", target.metric_id), resamples=150, batch_size=13
            )
            batched = bca_bootstrap(
                indices,
                fast,
                keys=("equivalence", target.metric_id),
                resamples=150,
                batch_size=31,
                batch_statistic=fast.batch,
                jackknife_values=fast.jackknife(),
            )
            assert batched.ci.lower == pytest.approx(serial.ci.lower, abs=1e-9)
            assert batched.ci.upper == pytest.approx(serial.ci.upper, abs=1e-9)
