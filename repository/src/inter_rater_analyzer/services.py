"""Application composition root. Widgets receive services rather than SQL handles."""

from dataclasses import dataclass
from pathlib import Path

from inter_rater_analyzer.analyses import ANALYSIS_MIGRATION, AnalysisRepository
from inter_rater_analyzer.analytics import analyze_criterion
from inter_rater_analyzer.artifacts import ARTIFACT_MIGRATION, ArtifactStore
from inter_rater_analyzer.backups import BackupService, recover_restore
from inter_rater_analyzer.bootstrap import bca_bootstrap
from inter_rater_analyzer.comparison import ComparisonService
from inter_rater_analyzer.config import RuntimePaths
from inter_rater_analyzer.database import Database
from inter_rater_analyzer.drafts import DRAFT_MIGRATION, DraftService
from inter_rater_analyzer.execution import EXECUTION_MIGRATION, ExecutionService
from inter_rater_analyzer.history import HistoryService
from inter_rater_analyzer.identity import MAPPING_MIGRATION, MappingRepository
from inter_rater_analyzer.metric_registry import MetricRegistry, get_registry
from inter_rater_analyzer.presets import PRESET_MIGRATION, PresetService
from inter_rater_analyzer.reports import REPORT_MIGRATION, ReportService
from inter_rater_analyzer.uncertainty import preflight_uncertainty, results_with_ci
from inter_rater_analyzer.versions import VersionService
from inter_rater_analyzer.workbooks import WorkbookService


@dataclass(frozen=True)
class Services:
    paths: RuntimePaths
    database: Database
    analyses: AnalysisRepository
    artifacts: ArtifactStore
    workbooks: WorkbookService
    drafts: DraftService
    metrics: MetricRegistry
    execution: ExecutionService
    versions: VersionService
    comparisons: ComparisonService
    presets: PresetService
    history: HistoryService
    reports: ReportService
    backups: BackupService

    bootstrap = staticmethod(bca_bootstrap)
    preflight_metrics = staticmethod(preflight_uncertainty)
    calculate_metrics = staticmethod(results_with_ci)
    analyze_criterion = staticmethod(analyze_criterion)

    @classmethod
    def open(cls, root: Path | None = None) -> Services:
        paths = RuntimePaths.resolve(root)
        recover_restore(paths.root)
        paths.initialize()
        database = Database(paths.database)
        database.initialize(
            (
                ANALYSIS_MIGRATION,
                ARTIFACT_MIGRATION,
                MAPPING_MIGRATION,
                DRAFT_MIGRATION,
                EXECUTION_MIGRATION,
                PRESET_MIGRATION,
                REPORT_MIGRATION,
            )
        )
        artifacts = ArtifactStore(paths, database)
        analyses = AnalysisRepository(database)
        workbooks = WorkbookService(artifacts, analyses, MappingRepository(database))
        drafts = DraftService(database, analyses, workbooks)
        execution = ExecutionService(database, drafts)
        return cls(
            paths,
            database,
            analyses,
            artifacts,
            workbooks,
            drafts,
            get_registry(),
            execution,
            VersionService(drafts),
            ComparisonService(execution),
            PresetService(drafts),
            HistoryService(database),
            ReportService(execution, paths),
            BackupService(paths, database),
        )
