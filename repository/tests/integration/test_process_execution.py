from inter_rater_analyzer.services import Services
from tests.integration.test_execution import prepared


def test_worker_schedule_preserves_bootstrap_results():
    from inter_rater_analyzer.analytics import analyze_workbook
    from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
    from inter_rater_analyzer.domain import RatingType
    from inter_rater_analyzer.ratings import NormalizedCriterion

    data = NormalizedCriterion(
        "Nominal",
        RatingType.NOMINAL,
        tuple(str(i) for i in range(18)),
        ("Rater A", "Rater B", "Rater C"),
        (("a", "a", "b"), ("b", "b", "b"), ("a", "b", "b")) * 6,
        ("a", "b"),
        None,
        None,
    )
    config = AnalysisConfiguration(
        (CriterionConfiguration("Nominal", RatingType.NOMINAL, metrics=("raw_agreement",)),)
    )
    serial = analyze_workbook((data,), config, version_key="stable")
    worker = analyze_workbook((data,), config, version_key="stable", worker_processes=True)
    assert serial == worker
    assert worker.criteria[0].metrics[0].bootstrap_resamples == 10000


def test_process_execution_matches_serial(tmp_path):
    services, state = prepared(tmp_path)
    result = services.execution.execute(state.version_id, worker_processes=True)
    assert result.criteria[0].metrics[0].estimate == 0
    assert Services.open(services.paths.root).execution.load(state.version_id)["result"]["ranking"]
