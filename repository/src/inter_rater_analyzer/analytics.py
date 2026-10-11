"""Headless criterion result pipeline, consumed by execution orchestration."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context

from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.continuous import exclude_items
from inter_rater_analyzer.diagnostics import ItemDiagnostic, diagnose_items
from inter_rater_analyzer.metric_registry import MetricResult
from inter_rater_analyzer.priority import ItemPriority, rank_items
from inter_rater_analyzer.priority_signals import ItemSignals, priority_signals
from inter_rater_analyzer.rater_diagnostics import RaterDiagnostic, diagnose_raters
from inter_rater_analyzer.ratings import NormalizedCriterion
from inter_rater_analyzer.summary import SummaryEntry, executive_summary
from inter_rater_analyzer.uncertainty import results_with_ci


@dataclass(frozen=True)
class CriterionResult:
    name: str
    metrics: tuple[MetricResult, ...]
    items: tuple[ItemDiagnostic, ...]
    raters: tuple[RaterDiagnostic, ...]
    signals: tuple[ItemSignals, ...]


def analyze_criterion(
    data: NormalizedCriterion,
    settings: CriterionConfiguration,
    *,
    confidence: float,
    version_key: str,
) -> CriterionResult:
    return CriterionResult(
        data.name,
        results_with_ci(data, settings, confidence=confidence, version_key=version_key),
        diagnose_items(data, settings),
        diagnose_raters(data, settings),
        priority_signals(data, settings),
    )


@dataclass(frozen=True)
class WorkbookResult:
    criteria: tuple[CriterionResult, ...]
    ranking: tuple[ItemPriority, ...]
    summary: tuple[SummaryEntry, ...]


def _criterion_job(
    job: tuple[NormalizedCriterion, CriterionConfiguration, float, str],
) -> CriterionResult:
    data, settings, confidence, key = job
    return analyze_criterion(data, settings, confidence=confidence, version_key=key)


def analyze_workbook(
    data: tuple[NormalizedCriterion, ...],
    config: AnalysisConfiguration,
    *,
    version_key: str,
    worker_processes: bool = False,
) -> WorkbookResult:
    settings = {criterion.name: criterion for criterion in config.criteria}
    excluded = {exclusion.item_id for exclusion in config.exclusions}
    included = tuple(exclude_items(criterion, excluded) for criterion in data)
    jobs = tuple(
        (criterion, settings[criterion.name], config.confidence, version_key)
        for criterion in included
    )
    if worker_processes:
        with ProcessPoolExecutor(
            max_workers=min(4, len(jobs)), mp_context=get_context("spawn")
        ) as pool:
            results = tuple(pool.map(_criterion_job, jobs))
    else:
        results = tuple(map(_criterion_job, jobs))
    ranking = rank_items(tuple(result.signals for result in results), config.weights)
    return WorkbookResult(results, ranking, executive_summary(results, included, ranking))
