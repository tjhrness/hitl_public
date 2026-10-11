import json
import subprocess
import sys

import numpy as np
import pytest
from scipy.stats import bootstrap

from inter_rater_analyzer.bootstrap import bca_bootstrap, child_seed
from inter_rater_analyzer.domain import DomainError


def test_bca_against_scipy_and_batch_invariance():
    values = np.arange(1, 21, dtype=float) ** 1.3
    seed = child_seed("version", "criterion", "metric", "pair")
    result = bca_bootstrap(
        values, lambda x: float(np.mean(x)), keys=("version", "criterion", "metric", "pair")
    )
    reference = bootstrap(
        (values,),
        np.mean,
        method="BCa",
        n_resamples=10000,
        rng=np.random.default_rng(seed),
        batch=256,
    )
    assert result.resamples == 10000
    assert result.ci.lower == pytest.approx(reference.confidence_interval.low)
    assert result.ci.upper == pytest.approx(reference.confidence_interval.high)
    assert (
        bca_bootstrap(
            values,
            lambda x: float(np.mean(x)),
            keys=("version", "criterion", "metric", "pair"),
            batch_size=7,
        )
        == result
    )


def test_row_dependence_and_restart_seed():
    values = np.column_stack((np.arange(1, 11, dtype=float), np.arange(1, 11, dtype=float) * 10))

    def statistic(sample):
        assert np.array_equal(sample[:, 1], sample[:, 0] * 10)
        return float(np.mean(sample[:, 0]))

    result = bca_bootstrap(values, statistic, keys=("a",))
    assert result.ci.lower < result.ci.upper
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import json; from inter_rater_analyzer.bootstrap import child_seed; "
            'print(json.dumps(child_seed("a")))',
        ]
    )
    assert json.loads(output) == child_seed("a")
    assert child_seed("a") != child_seed("b")


def test_degenerate_bca_explicit_failure():
    with pytest.raises(DomainError):
        bca_bootstrap(np.ones(8), lambda x: float(np.mean(x)), keys=("constant",))
