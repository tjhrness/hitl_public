"""Collect structural problems without exposing original rater identities."""

from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.ingestion import RawCriterion


def validate_structure(criteria: tuple[RawCriterion, ...]) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    if not 1 <= len(criteria) <= 10:
        findings.append(
            ValidationFinding(
                "VALIDATION_SHEET_COUNT",
                "Expected 1–10 visible worksheets.",
                "Keep 1–10 visible criterion worksheets.",
            )
        )
    baseline_ids: set[str] | None = None
    baseline_raters: tuple[str, ...] | None = None
    for criterion in criteria:

        def add(
            code: str,
            message: str,
            action: str,
            row: int | None = None,
            worksheet: str = criterion.name,
        ) -> None:
            findings.append(
                ValidationFinding(
                    "VALIDATION_" + code, message, action, worksheet=worksheet, row=row
                )
            )

        raters = tuple(
            header[len("Rater:") :].strip().casefold() for header in criterion.rater_headers
        )
        if not 2 <= len(raters) <= 10:
            add(
                "RATER_COUNT",
                "Expected 2–10 rater columns.",
                "Add 2–10 columns starting with Rater:.",
            )
        if any(not rater for rater in raters):
            add(
                "RATER_BLANK",
                "A rater header has no identity.",
                "Supply a nonblank rater identity.",
            )
        if len(set(raters)) != len(raters):
            add("RATER_DUPLICATE", "Rater identities repeat.", "Use a unique identity per rater.")
        if not 1 <= len(criterion.rows) <= 1000:
            add("ITEM_COUNT", "Expected 1–1,000 visible items.", "Use 1–1,000 visible Item IDs.")
        ids: set[str] = set()
        for record in criterion.rows:
            item = str(record.item_id).strip() if record.item_id is not None else ""
            if not item:
                add("ID_BLANK", "Item ID is blank.", "Enter an Item ID.", record.excel_row)
            elif item in ids:
                add(
                    "ID_DUPLICATE", "Item ID is repeated.", "Use unique Item IDs.", record.excel_row
                )
            ids.add(item)
            if len(record.ratings) != len(raters) or any(
                value is None or isinstance(value, str) and not value.strip()
                for value in record.ratings
            ):
                add(
                    "MISSING_RATING",
                    "A rating is missing.",
                    "Fill every rater cell.",
                    record.excel_row,
                )
        if baseline_ids is not None and ids != baseline_ids:
            add("ID_SET", "Item IDs differ across criteria.", "Use the same Item ID set.")
        if baseline_raters is not None and raters != baseline_raters:
            code = "RATER_ORDER" if set(raters) == set(baseline_raters) else "RATER_SET"
            add(code, "Raters differ across criteria.", "Use the same raters in the same order.")
        if baseline_ids is None:
            baseline_ids, baseline_raters = ids, raters
    return tuple(findings)
