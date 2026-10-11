import pytest

from inter_rater_analyzer.canonical import canonicalize
from inter_rater_analyzer.domain import DomainError
from inter_rater_analyzer.ingestion import RawCriterion, RawRow


def raw(name, items=("Q1", "Q2"), headers=("Rater:Alice", "Rater:Bob")):
    return RawCriterion(
        name,
        headers,
        tuple(RawRow(index + 2, item, (item, item)) for index, item in enumerate(items)),
    )


def test_canonical_alignment():
    data, mappings = canonicalize((raw("A"), raw("B", ("Q2", "Q1"))))
    assert data.item_ids == ("Q1", "Q2")
    assert data.item_count == 2
    assert data.rater_count == 2
    assert data.criterion_names == ("A", "B")
    assert data.ratings("A", "Q1") == data.ratings("B", "Q1") == ("Q1", "Q1")
    assert data.criteria[1].rows[0].excel_row == 3
    assert mappings[0].alias == "Rater A"


@pytest.mark.parametrize(
    "other",
    [
        raw("B", ("Q1",)),
        raw("B", ("Q1", "Q3")),
        raw("B", headers=("Rater:Bob", "Rater:Alice")),
        raw("B", headers=("Rater:Alice", "Rater:Carol")),
    ],
)
def test_incompatible_criteria(other):
    with pytest.raises(DomainError):
        canonicalize((raw("A"), other))
