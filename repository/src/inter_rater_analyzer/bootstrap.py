"""Deterministic batched BCa bootstrap, resampling complete item rows."""

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
from numpy.typing import NDArray

from inter_rater_analyzer.config import BOOTSTRAP_RESAMPLES, MASTER_SEED
from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.metric_registry import ConfidenceInterval

type NumericArray = NDArray[np.float64]
type Statistic = Callable[[NumericArray], float]


def child_seed(*keys: str, master_seed: int = MASTER_SEED) -> int:
    encoded = json.dumps([master_seed, *keys], ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")


@dataclass(frozen=True)
class BootstrapResult:
    ci: ConfidenceInterval
    resamples: int
    seed: int
    seed_scheme: str = "sha256-json-utf8-first64-big-v1"


def bca_bootstrap(
    values: NumericArray,
    statistic: Statistic,
    *,
    keys: tuple[str, ...],
    confidence: float = 95.0,
    resamples: int = BOOTSTRAP_RESAMPLES,
    batch_size: int = 256,
    batch_statistic: Callable[[NumericArray], NumericArray] | None = None,
    jackknife_values: NumericArray | None = None,
) -> BootstrapResult:
    if values.ndim < 1 or len(values) < 2 or resamples < 2 or batch_size < 1:
        raise DomainError(
            ErrorCode.STAT_UNDEFINED, "BCa requires multiple rows and valid batch settings."
        )
    if not math.isfinite(confidence) or not 0 < confidence < 100:
        raise DomainError(
            ErrorCode.VALIDATION_VALUE, "Confidence must lie strictly between 0 and 100."
        )
    n = len(values)
    seed = child_seed(*keys)
    rng = np.random.default_rng(seed)
    observed = statistic(values)
    estimates = np.empty(resamples, dtype=np.float64)
    for start in range(0, resamples, batch_size):
        size = min(batch_size, resamples - start)
        indices = rng.integers(0, n, size=(size, n))
        if batch_statistic is not None:
            estimates[start : start + size] = batch_statistic(values[indices])
        else:
            for offset, index in enumerate(indices):
                estimates[start + offset] = statistic(values[index])
    jackknife = (
        jackknife_values
        if jackknife_values is not None
        else np.asarray(
            [statistic(np.delete(values, index, axis=0)) for index in range(n)], dtype=np.float64
        )
    )
    if (
        not math.isfinite(observed)
        or not np.all(np.isfinite(estimates))
        or not np.all(np.isfinite(jackknife))
    ):
        raise DomainError(ErrorCode.STAT_UNDEFINED, "BCa encountered a noncomputable resample.")
    differences = float(np.mean(jackknife)) - jackknife
    denominator = 6 * float(np.sum(differences**2)) ** 1.5
    # Equivalent reductions can differ at machine precision. Give numerical ties half
    # weight so batch shape and summation order cannot change BCa's discrete bias count.
    ties = np.isclose(estimates, observed, rtol=1e-12, atol=1e-14)
    proportion = (
        int(np.count_nonzero((estimates < observed) & ~ties)) + 0.5 * int(np.count_nonzero(ties))
    ) / resamples
    if denominator == 0 or not 0 < proportion < 1 or float(np.ptp(estimates)) == 0:
        raise DomainError(
            ErrorCode.STAT_UNDEFINED, "BCa interval is undefined for degenerate data."
        )
    acceleration = float(np.sum(differences**3)) / denominator
    normal = NormalDist()
    bias = normal.inv_cdf(proportion)
    tail = (1 - confidence / 100) / 2
    probabilities: list[float] = []
    for probability in (tail, 1 - tail):
        z = normal.inv_cdf(probability)
        divisor = 1 - acceleration * (bias + z)
        if divisor == 0:
            raise DomainError(ErrorCode.STAT_UNDEFINED, "BCa adjustment is undefined.")
        probabilities.append(normal.cdf(bias + (bias + z) / divisor))
    if probabilities[0] > probabilities[1]:
        raise DomainError(ErrorCode.STAT_UNDEFINED, "BCa adjustment reverses interval bounds.")
    limits = np.quantile(estimates, probabilities, method="linear")
    return BootstrapResult(
        ConfidenceInterval(float(limits[0]), float(limits[1]), confidence, "BCa"), resamples, seed
    )
