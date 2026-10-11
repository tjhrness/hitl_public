from dataclasses import replace

import pytest

from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.identity import Criterion, RatingRow
from inter_rater_analyzer.ratings import normalize_ratings


def test_existing_warnings_do_not_suppress_imbalance_on_report_recalculation():
    data = normalize_ratings(
        Criterion(
            "A",
            ("Rater A", "Rater B"),
            tuple(RatingRow(i + 2, str(i), ("a", "a")) for i in range(5)),
        ),
        RatingType.NOMINAL,
    )
    warned = replace(data, findings=quality_warnings(data))
    assert "WARNING_SEVERE_IMBALANCE" in {w.code for w in quality_warnings(warned)}


@pytest.mark.parametrize("count,expected", [(29, True), (30, False)])
def test_sample_size(count, expected):
    data = normalize_ratings(
        Criterion(
            "A",
            ("Rater A", "Rater B"),
            tuple(RatingRow(i + 2, str(i), ("a", "b")) for i in range(count)),
        ),
        RatingType.NOMINAL,
    )
    assert ("WARNING_SAMPLE_SIZE" in {f.code for f in quality_warnings(data)}) is expected


@pytest.mark.parametrize(
    "dominant,expected",
    [
        (79, None),
        (80, "WARNING_IMBALANCE"),
        (89, "WARNING_IMBALANCE"),
        (90, "WARNING_SEVERE_IMBALANCE"),
    ],
)
def test_imbalance_threshold(dominant, expected):
    values = ["a"] * dominant + ["b"] * (100 - dominant)
    data = normalize_ratings(
        Criterion(
            "A",
            ("Rater A", "Rater B"),
            tuple(RatingRow(i + 2, str(i), (values[2 * i], values[2 * i + 1])) for i in range(50)),
        ),
        RatingType.NOMINAL,
    )
    codes = [f.code for f in quality_warnings(data)]
    assert codes == ([expected] if expected else [])


@pytest.mark.parametrize("count,expected", [(20, False), (21, True)])
def test_cardinality(count, expected):
    data = normalize_ratings(
        Criterion(
            "A",
            ("Rater A", "Rater B"),
            tuple(RatingRow(i + 2, str(i), (str(i), str(i))) for i in range(count)),
        ),
        RatingType.NOMINAL,
    )
    assert ("WARNING_CARDINALITY" in {f.code for f in quality_warnings(data)}) is expected
