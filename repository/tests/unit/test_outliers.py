import pytest

from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.outliers import outlier_flags


@pytest.mark.parametrize(
    "row,expected",
    [
        (("a", "a", "a", "a", "b"), (False, False, False, False, True)),
        (("a", "a", "a", "b", "b"), (False,) * 5),
        (("a", "b"), (False, False)),
    ],
)
def test_singleton_rule(row, expected):
    assert outlier_flags(row, RatingType.NOMINAL) == expected


def test_ordinal_main_cluster_and_boundary():
    assert outlier_flags(("a", "a", "c"), RatingType.ORDINAL, order=("a", "b", "c")) == (
        False,
        False,
        True,
    )
    assert outlier_flags(("a", "b", "c"), RatingType.ORDINAL, order=("a", "b", "c")) == (False,) * 3


def test_continuous_mad_zero_and_tolerance():
    assert outlier_flags((1.0, 1.0, 2.0), RatingType.CONTINUOUS, tolerance=1) == (False,) * 3
    assert outlier_flags((1.0, 1.0, 2.01), RatingType.CONTINUOUS, tolerance=1) == (
        False,
        False,
        True,
    )
    assert outlier_flags((1.0, 2.0), RatingType.CONTINUOUS) == (False, False)
    assert outlier_flags((1.0, 2.0, 3.0, 4.0, 100.0), RatingType.CONTINUOUS)[-1]
