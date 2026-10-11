from dataclasses import asdict

import pytest

from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.identity import normalize_criterion
from inter_rater_analyzer.ingestion import RawCriterion, RawRow


def test_identity_normalization_and_public_privacy():
    raw = RawCriterion(
        "Quality",
        ("Rater: Alice ", "Rater:Bob"),
        (RawRow(2, " Q1 ", ("yes", "no")), RawRow(3, "q1", ("no", "yes"))),
    )
    public, internal = normalize_criterion(raw)
    assert [row.item_id for row in public.rows] == ["Q1", "q1"]
    assert public.raters == ("Rater A", "Rater B")
    assert internal[0].normalized == "alice"
    assert "Alice" not in repr(public) + str(asdict(public))


@pytest.mark.parametrize(
    "headers,items",
    [
        (("Rater:Alice", "Rater: ALICE "), ("Q1",)),
        (("Rater:", "Rater:Bob"), ("Q1",)),
        (("Rater:Alice", "Rater:Bob"), ("Q1", " Q1 ")),
        (("Rater:Alice", "Rater:Bob"), (" ",)),
    ],
)
def test_invalid_identities(headers, items):
    raw = RawCriterion(
        "Quality",
        headers,
        tuple(RawRow(i + 2, item, ("yes", "no")) for i, item in enumerate(items)),
    )
    with pytest.raises(DomainError):
        normalize_criterion(raw)
