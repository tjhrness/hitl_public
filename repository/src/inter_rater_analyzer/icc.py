"""Two-way random-effects average-measures ICC(A,k) and ICC(C,k)."""

from functools import partial

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.continuous import continuous_preflight
from inter_rater_analyzer.domain import DomainError, ErrorCode, MetricScope, RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult
from inter_rater_analyzer.ratings import NormalizedCriterion


def icc(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, consistency: bool = False
) -> tuple[MetricResult, ...]:
    n, k = len(data.values), len(data.raters)
    if n < 2 or k < 2:
        raise DomainError(
            ErrorCode.STAT_UNDEFINED, "ICC requires at least two items and two raters."
        )
    values = tuple(tuple(float(value) for value in row) for row in data.values)
    rows = tuple(sum(row) / k for row in values)
    columns = tuple(sum(row[j] for row in values) / n for j in range(k))
    grand = sum(rows) / n
    ms_items = k * sum((value - grand) ** 2 for value in rows) / (n - 1)
    ms_raters = n * sum((value - grand) ** 2 for value in columns) / (k - 1)
    ms_error = sum(
        (values[i][j] - rows[i] - columns[j] + grand) ** 2 for i in range(n) for j in range(k)
    ) / ((n - 1) * (k - 1))
    denominator = ms_items if consistency else ms_items + (ms_raters - ms_error) / n
    if ms_items <= 0 or denominator <= 0:
        raise DomainError(ErrorCode.STAT_UNDEFINED, "ICC has undefined variance components.")
    return (
        MetricResult(
            "icc_consistency" if consistency else "icc_absolute",
            data.name,
            (ms_items - ms_error) / denominator,
            components=(
                ("MS_items", ms_items),
                ("MS_raters", ms_raters),
                ("MS_error", ms_error),
                ("variance_items", (ms_items - ms_error) / k),
                ("variance_raters", (ms_raters - ms_error) / n),
                ("variance_error", ms_error),
            ),
        ),
    )


def preflight(
    data: NormalizedCriterion, settings: CriterionConfiguration, *, consistency: bool = False
) -> tuple[ValidationFinding, ...]:
    findings = continuous_preflight(data, settings)
    if findings:
        return findings
    try:
        icc(data, settings, consistency=consistency)
    except DomainError as error:
        return (
            ValidationFinding(
                "STAT_ICC_UNDEFINED",
                error.message,
                "Deselect ICC or supply nondegenerate repeated ratings.",
            ),
        )
    return ()


def register_metrics(registry: MetricRegistry) -> None:
    for consistency in (False, True):
        registry.register(
            MetricDefinition(
                "icc_consistency" if consistency else "icc_absolute",
                "ICC(C,k)" if consistency else "ICC(A,k)",
                (RatingType.CONTINUOUS,),
                MetricScope.OVERALL,
                True,
                ("Two items and two raters", "Nondegenerate ANOVA components"),
                False,
                False,
                "icc",
                "Two-way random-effects average measures; "
                "A,k=(MS_items-MS_error)/(MS_items+(MS_raters-MS_error)/n); "
                "C,k=(MS_items-MS_error)/MS_items. No single-rater result is exposed.",
                "1.0",
                partial(icc, consistency=consistency),
                partial(preflight, consistency=consistency),
            )
        )
