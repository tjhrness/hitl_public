"""Whole-row sufficient statistics for batched bootstrap and exact leave-one-out estimates."""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from inter_rater_analyzer.bootstrap import NumericArray
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.metric_registry import MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion

type Reducer = Callable[[NumericArray, int], NumericArray]


@dataclass(frozen=True)
class PreparedStatistic:
    features: NumericArray
    reduce: Reducer

    def __call__(self, indices: NumericArray) -> float:
        return float(
            self.reduce(
                self.features[indices.astype(np.int64)].mean(axis=0, keepdims=True), len(indices)
            )[0]
        )

    def batch(self, indices: NumericArray) -> NumericArray:
        rows = indices.astype(np.int64)
        if self.features.shape[1] == 1:
            means = self.features[rows].mean(axis=1)
        else:
            # The same row draws, represented as multiplicities, avoid a B x N x D copy.
            n = len(self.features)
            offsets = np.arange(len(rows))[:, None] * n
            counts = np.bincount((rows + offsets).ravel(), minlength=len(rows) * n)
            means = counts.reshape(len(rows), n) @ self.features / rows.shape[1]
        return self.reduce(means, indices.shape[1])

    def jackknife(self) -> NumericArray:
        n = len(self.features)
        return self.reduce((self.features.sum(axis=0) - self.features) / (n - 1), n - 1)


def prepare_statistic(
    data: NormalizedCriterion, settings: CriterionConfiguration, target: MetricResult
) -> PreparedStatistic:
    metric = target.metric_id
    categories = settings.ordinal_order or data.categories
    codes = {value: i for i, value in enumerate(categories)}
    values = (
        np.asarray(data.values, dtype=np.float64)
        if data.rating_type is RatingType.CONTINUOUS
        else np.asarray([[codes[v] for v in row] for row in data.values], dtype=np.float64)
    )
    k = values.shape[1]
    if metric == "lin_ccc" or metric.startswith("icc_"):
        values = values - values.mean()
    pairs = (
        tuple(combinations(range(k), 2))
        if target.pair is None
        else ((data.raters.index(target.pair[0]), data.raters.index(target.pair[1])),)
    )
    left = values[:, [p[0] for p in pairs]]
    right = values[:, [p[1] for p in pairs]]
    difference = left - right

    def average(means: NumericArray, n: int) -> NumericArray:
        return means.mean(axis=1)

    if metric in (
        "raw_agreement",
        "pairwise_agreement",
        "confusion_matrix",
        "practical_agreement",
        "mae",
        "rmse",
        "bland_altman",
    ):
        if metric in ("raw_agreement", "pairwise_agreement", "confusion_matrix"):
            features = (difference == 0).astype(np.float64) * 100
        elif metric == "practical_agreement":
            features = (np.abs(difference) <= settings.tolerance).astype(np.float64) * 100
        elif metric == "mae":
            features = np.abs(difference)
        elif metric == "rmse":
            features = difference**2
        else:
            features = difference
        if metric == "rmse":

            def root_average(means: NumericArray, n: int) -> NumericArray:
                return np.sqrt(means).mean(axis=1)

            return PreparedStatistic(features, root_average)
        return PreparedStatistic(features.mean(axis=1, keepdims=True), average)
    if metric == "lin_ccc":
        features = np.column_stack(
            (left[:, 0], right[:, 0], left[:, 0] ** 2, right[:, 0] ** 2, left[:, 0] * right[:, 0])
        )

        def ccc(means: NumericArray, n: int) -> NumericArray:
            x, y, xx, yy, xy = means.T
            return 2 * (xy - x * y) / (xx + yy - 2 * x * y)

        return PreparedStatistic(features, ccc)
    if metric.startswith("icc_"):
        row_mean = values.mean(axis=1)
        features = np.column_stack((row_mean, row_mean**2, (values**2).mean(axis=1), values))

        def icc(means: NumericArray, n: int) -> NumericArray:
            grand = means[:, 0]
            ss_rows = k * n * (means[:, 1] - grand**2)
            ss_columns = n * ((means[:, 3:] - grand[:, None]) ** 2).sum(axis=1)
            ms_rows = ss_rows / (n - 1)
            ms_columns = ss_columns / (k - 1)
            ms_error = (n * k * (means[:, 2] - grand**2) - ss_rows - ss_columns) / (
                (n - 1) * (k - 1)
            )
            denominator = (
                ms_rows if metric == "icc_consistency" else ms_rows + (ms_columns - ms_error) / n
            )
            return np.where(
                (ms_rows > 0) & (denominator > 0), (ms_rows - ms_error) / denominator, np.nan
            )

        return PreparedStatistic(features, icc)
    q = len(categories)
    ranks = np.arange(q, dtype=np.float64)
    distance = np.abs(ranks[:, None] - ranks[None, :])
    if metric in ("cohen_kappa", "linear_kappa", "quadratic_kappa"):
        weights = (
            (distance != 0).astype(np.float64)
            if metric == "cohen_kappa"
            else distance ** (2 if metric == "quadratic_kappa" else 1)
        )
        features = np.column_stack(
            (
                left[:, 0, None] == ranks,
                right[:, 0, None] == ranks,
                weights[left[:, 0].astype(int), right[:, 0].astype(int)],
            )
        ).astype(np.float64)

        def kappa(means: NumericArray, n: int) -> NumericArray:
            expected = np.einsum("bi,ij,bj->b", means[:, :q], weights, means[:, q : 2 * q])
            return 1 - means[:, -1] / expected

        return PreparedStatistic(features, kappa)
    proportions = (values[:, :, None] == ranks).mean(axis=1)
    unequal = (difference != 0).mean(axis=1)
    if metric in ("fleiss_kappa", "alpha_nominal", "gwet_ac1", "gwet_ac2"):
        agreement = (
            1 - (difference**2).mean(axis=1) / (q - 1) ** 2 if metric == "gwet_ac2" else 1 - unequal
        )
        features = np.column_stack((proportions, agreement))

        def panel(means: NumericArray, n: int) -> NumericArray:
            p = means[:, :q]
            observed = means[:, -1]
            squared = (p**2).sum(axis=1)
            if metric == "alpha_nominal":
                return 1 - (1 - observed) / ((1 - squared) * n * k / (n * k - 1))
            if metric.startswith("gwet"):
                weight_sum = (
                    float((1 - distance**2 / (q - 1) ** 2).sum())
                    if metric == "gwet_ac2"
                    else float(q)
                )
                expected = weight_sum * (p * (1 - p)).sum(axis=1) / (q * (q - 1))
            else:
                expected = squared
            return (observed - expected) / (1 - expected)

        return PreparedStatistic(features, panel)
    if metric == "alpha_ordinal":
        # Pair-category frequencies preserve the dependence of ordinal distance on pooled counts.
        coincidences = np.stack(
            [((left == a) & (right == b)).mean(axis=1) for a in range(q) for b in range(q)], axis=1
        )
        features = np.column_stack((proportions, coincidences))

        def ordinal_alpha(means: NumericArray, n: int) -> NumericArray:
            p = means[:, :q]
            midpoints = np.cumsum(p, axis=1) - p / 2
            distances = (midpoints[:, :, None] - midpoints[:, None, :]) ** 2
            observed = (means[:, q:].reshape(-1, q, q) * distances).sum(axis=(1, 2))
            expected = (
                (p[:, :, None] * p[:, None, :] * distances).sum(axis=(1, 2)) * n * k / (n * k - 1)
            )
            return 1 - observed / expected

        return PreparedStatistic(features, ordinal_alpha)
    raise ValueError("No vectorized statistic for selected metric")
