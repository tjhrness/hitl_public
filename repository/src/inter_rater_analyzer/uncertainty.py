"""Validated analytic agreement intervals and row-wise BCa metric adapters."""

import json
import math
from dataclasses import replace
from statistics import NormalDist

import numpy as np

from inter_rater_analyzer.bootstrap import NumericArray, Statistic, bca_bootstrap
from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.fast_statistics import prepare_statistic
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.interpretation import interpret_results
from inter_rater_analyzer.metric_execution import execute_metrics
from inter_rater_analyzer.metric_registry import ConfidenceInterval, MetricResult, get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion
from inter_rater_analyzer.significance import add_significance


def analytic_agreement(result: MetricResult, raters: int) -> bool:
    return result.metric_id in ("pairwise_agreement", "confusion_matrix") or (
        result.metric_id == "raw_agreement" and raters == 2
    )


def wilson(estimate: float, n: int, confidence: float) -> ConfidenceInterval:
    p = estimate / 100
    z = NormalDist().inv_cdf((1 + confidence / 100) / 2)
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return ConfidenceInterval(
        100 * (center - half), 100 * (center + half), confidence, "Wilson score"
    )


def metric_statistic(
    data: NormalizedCriterion, settings: CriterionConfiguration, target: MetricResult
) -> Statistic:
    definition = get_registry().get(target.metric_id)

    def statistic(indices: NumericArray) -> float:
        rows = tuple(data.values[int(index)] for index in indices)
        sample = replace(data, values=rows, item_ids=tuple(str(i) for i in range(len(rows))))
        return next(
            result.estimate
            for result in definition.calculate(sample, settings)
            if result.pair == target.pair
        )

    return statistic


def preflight_uncertainty(
    data: NormalizedCriterion, settings: CriterionConfiguration
) -> tuple[ValidationFinding, ...]:
    try:
        results = execute_metrics(data, settings)
        indices = np.arange(len(data.values), dtype=np.float64)
        for result in results:
            if analytic_agreement(result, len(data.raters)):
                continue
            if len(indices) < 3:
                raise ValueError("BCa requires at least three items for this metric.")
            statistic = prepare_statistic(data, settings, result)
            jackknife = statistic.jackknife()
            if max(jackknife) == min(jackknife) or not all(math.isfinite(v) for v in jackknife):
                raise ValueError("Degenerate jackknife")
    except DomainError, ValueError, ZeroDivisionError:
        return (
            ValidationFinding(
                "STAT_CI_UNDEFINED",
                "A selected metric cannot produce its required confidence interval.",
                "Deselect the noncomputable metric or provide more variable complete item rows.",
            ),
        )
    return ()


def results_with_ci(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
    *,
    confidence: float,
    version_key: str,
) -> tuple[MetricResult, ...]:
    if not math.isfinite(confidence) or not 0 < confidence < 100:
        raise DomainError(ErrorCode.VALIDATION_VALUE, "Confidence must be between 0 and 100.")
    findings = preflight_uncertainty(data, settings)
    if findings:
        raise DomainError(ErrorCode.STAT_UNDEFINED, findings[0].message)
    results: list[MetricResult] = []
    indices = np.arange(len(data.values), dtype=np.float64)
    for result in execute_metrics(data, settings):
        if analytic_agreement(result, len(data.raters)):
            results.append(
                replace(result, ci=wilson(result.estimate, len(data.values), confidence))
            )
            continue
        statistic = prepare_statistic(data, settings, result)
        interval = bca_bootstrap(
            indices,
            statistic,
            batch_statistic=statistic.batch,
            jackknife_values=statistic.jackknife(),
            batch_size=64,
            keys=(version_key, data.name, result.metric_id, json.dumps(result.pair)),
            confidence=confidence,
        )
        results.append(
            replace(
                result,
                ci=interval.ci,
                bootstrap_resamples=interval.resamples,
                bootstrap_seed=interval.seed,
                bootstrap_seed_scheme=interval.seed_scheme,
                implementation_version="1.1",
            )
        )
    return interpret_results(add_significance(tuple(results), data), data)
