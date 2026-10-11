import pytest

from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.identity import Criterion, RatingRow
from inter_rater_analyzer.ratings import normalize_ratings


def criterion(values):
    return Criterion(
        "Quality",
        ("Rater A", "Rater B"),
        tuple(RatingRow(i + 2, str(i), pair) for i, pair in enumerate(values)),
    )


def test_categories_and_punctuation():
    result = normalize_ratings(
        criterion([(" Yes ", "YES"), ("a-b", "a/b"), (1, "one")]), RatingType.NOMINAL
    )
    assert not result.findings
    assert result.values[0] == ("yes", "yes")
    assert "a-b" in result.categories and "a/b" in result.categories
    assert 1 in result.categories


def test_numeric_normalization():
    result = normalize_ratings(criterion([("1.5", 2), ("-2e1", "3")]), RatingType.CONTINUOUS)
    assert result.minimum == -20 and result.maximum == 3
    assert result.values == ((1.5, 2.0), (-20.0, 3.0))
    ordinal = normalize_ratings(criterion([("1", 1), (" low ", "HIGH")]), RatingType.ORDINAL)
    assert ordinal.categories == (1.0, "high", "low")


@pytest.mark.parametrize("value", [None, "", "one", "1,000", float("nan"), float("inf"), True])
def test_invalid_continuous(value):
    result = normalize_ratings(criterion([(value, 2)]), RatingType.CONTINUOUS)
    assert result.findings[0].code == "VALIDATION_RATING_TYPE"


def test_binary_cardinality():
    result = normalize_ratings(criterion([("yes", "no"), ("maybe", "no")]), RatingType.BINARY)
    assert result.findings[0].code == "VALIDATION_BINARY_CATEGORIES"
