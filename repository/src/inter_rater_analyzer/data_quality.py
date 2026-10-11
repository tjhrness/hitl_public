"""Nonblocking warning rules with explicit observed values and caveats."""

from collections import Counter

from inter_rater_analyzer.domain import RatingType, ValidationSeverity
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.ratings import NormalizedCriterion


def quality_warnings(data: NormalizedCriterion) -> tuple[ValidationFinding, ...]:
    warnings: list[ValidationFinding] = []

    def add(code: str, message: str) -> None:
        warnings.append(
            ValidationFinding(
                code,
                message,
                "Review and acknowledge this limitation before execution.",
                ValidationSeverity.WARNING,
                data.name,
            )
        )

    if len(data.item_ids) < 30:
        add(
            "WARNING_SAMPLE_SIZE",
            f"{len(data.item_ids)} included items; fewer than 30 may yield unstable estimates.",
        )
    if data.rating_type is not RatingType.CONTINUOUS and not any(
        finding.severity is ValidationSeverity.ERROR for finding in data.findings
    ):
        counts = Counter(value for row in data.values for value in row)
        total = counts.total()
        if total:
            largest = max(counts.values())
            percent = 100 * largest / total
            if largest * 10 >= total * 9:
                add(
                    "WARNING_SEVERE_IMBALANCE",
                    f"Dominant category is {percent:g}% (>=90%); "
                    "chance-adjusted metrics may mislead.",
                )
            elif largest * 5 >= total * 4:
                add(
                    "WARNING_IMBALANCE",
                    f"Dominant category is {percent:g}% (>=80%); "
                    "compare raw agreement and AC metrics.",
                )
        if len(counts) > 20:
            add(
                "WARNING_CARDINALITY",
                f"{len(counts)} categories (>20); sparse categories may make estimates unstable.",
            )
    return tuple(warnings)
