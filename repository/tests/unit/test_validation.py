import pytest

from inter_rater_analyzer.ingestion import RawCriterion, RawRow
from inter_rater_analyzer.validation import validate_structure


def criterion(headers=("Rater:A", "Rater:B"), rows=None, name="A"):
    return RawCriterion(name, headers, rows or (RawRow(2, "Q1", ("yes", "no")),))


@pytest.mark.parametrize(
    "criteria,code",
    [
        ((), "VALIDATION_SHEET_COUNT"),
        (tuple(criterion(name=str(i)) for i in range(11)), "VALIDATION_SHEET_COUNT"),
        ((criterion(headers=("Rater:A",)),), "VALIDATION_RATER_COUNT"),
        ((criterion(headers=tuple(f"Rater:{i}" for i in range(11))),), "VALIDATION_RATER_COUNT"),
        ((criterion(headers=("Rater:A", "Rater: a ")),), "VALIDATION_RATER_DUPLICATE"),
        ((criterion(rows=(RawRow(2, "", ("yes", "no")),)),), "VALIDATION_ID_BLANK"),
        (
            (criterion(rows=(RawRow(2, "Q1", ("yes", "no")), RawRow(3, " Q1 ", ("yes", "no")))),),
            "VALIDATION_ID_DUPLICATE",
        ),
        ((criterion(rows=(RawRow(2, "Q1", (None, "no")),)),), "VALIDATION_MISSING_RATING"),
        (
            (criterion(rows=tuple(RawRow(i + 2, str(i), ("a", "b")) for i in range(1001))),),
            "VALIDATION_ITEM_COUNT",
        ),
        (
            (criterion(), criterion(rows=(RawRow(2, "Q2", ("yes", "no")),), name="B")),
            "VALIDATION_ID_SET",
        ),
        (
            (criterion(), criterion(headers=("Rater:B", "Rater:A"), name="B")),
            "VALIDATION_RATER_ORDER",
        ),
        (
            (criterion(), criterion(headers=("Rater:A", "Rater:C"), name="B")),
            "VALIDATION_RATER_SET",
        ),
    ],
)
def test_structural_rules(criteria, code):
    findings = validate_structure(criteria)
    assert code in {finding.code for finding in findings}
    assert all(finding.corrective_action for finding in findings)


def test_multiple_findings_without_identity_disclosure():
    findings = validate_structure(
        (criterion(headers=("Rater:Alice",), rows=(RawRow(2, "", (None,)),)),)
    )
    assert len(findings) >= 3
    assert "Alice" not in repr(findings)
