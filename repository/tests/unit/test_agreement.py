from dataclasses import replace

import pytest

from inter_rater_analyzer.configuration import CriterionConfiguration
from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.identity import Criterion, RatingRow
from inter_rater_analyzer.metric_execution import execute_metrics
from inter_rater_analyzer.ratings import normalize_ratings


def data(rows):
    aliases = tuple(f"Rater {chr(65 + i)}" for i in range(len(rows[0])))
    return normalize_ratings(
        Criterion(
            "A", aliases, tuple(RatingRow(i + 2, str(i), tuple(row)) for i, row in enumerate(rows))
        ),
        RatingType.NOMINAL,
    )


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([["a", "a"], ["a", "b"]], 50),
        ([["a", "a", "b"], ["b", "b", "b"]], 100 * 4 / 6),
        ([["a", "a", "a", "b", "b"]], 40),
        ([["a", "b", "c"]], 0),
    ],
)
def test_raw_agreement_golden(rows, expected):
    current = data(rows)
    settings = CriterionConfiguration("A", RatingType.NOMINAL, metrics=("raw_agreement",))
    assert execute_metrics(current, settings)[0].estimate == pytest.approx(expected)
    assert execute_metrics(replace(current, values=tuple(reversed(current.values))), settings)[
        0
    ].estimate == pytest.approx(expected)


def test_pairwise_confusion_and_normalization():
    current = data([[" Yes ", "YES"], ["no", "yes"], ["no", "no"]])
    settings = CriterionConfiguration(
        "A", RatingType.NOMINAL, metrics=("pairwise_agreement", "confusion_matrix")
    )
    results = execute_metrics(current, settings)
    assert results[0].estimate == pytest.approx(200 / 3)
    assert results[0].pair == ("Rater A", "Rater B")
    assert results[1].confusion.categories == ("no", "yes")
    assert results[1].confusion.counts == ((1, 1), (0, 1))
