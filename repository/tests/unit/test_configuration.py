from dataclasses import replace
from decimal import Decimal

import pytest

from inter_rater_analyzer.configuration import (
    AnalysisConfiguration,
    CriterionConfiguration,
    Exclusion,
    PrioritySignal,
    SignalWeight,
    recommended_tolerance,
    validate_configuration,
)
from inter_rater_analyzer.domain import DomainError, RatingType
from inter_rater_analyzer.ratings import normalize_ratings
from tests.unit.test_ratings import criterion


def configured():
    data = normalize_ratings(criterion([(1, 3), (2, 4)]), RatingType.CONTINUOUS)
    config = AnalysisConfiguration(
        (CriterionConfiguration("Quality", RatingType.CONTINUOUS, tolerance=0.15),),
        weights=(SignalWeight(PrioritySignal.PAIRWISE, Decimal("100")),),
    )
    return config, (data,)


def test_valid_snapshot_and_tolerance():
    config, data = configured()
    assert validate_configuration(config, data) == config
    assert recommended_tolerance(data[0]) == pytest.approx(0.15)


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", 0),
        ("confidence", 100),
        ("confidence", float("nan")),
        ("alpha", 0),
        ("alpha", 1),
        ("alpha", float("inf")),
        ("weights", (SignalWeight(PrioritySignal.PAIRWISE, Decimal("99.99")),)),
        ("exclusions", (Exclusion("missing", "because"),)),
        ("exclusions", (Exclusion("0", " "),)),
    ],
)
def test_invalid_configuration(field, value):
    config, data = configured()
    with pytest.raises(DomainError):
        validate_configuration(replace(config, **{field: value}), data)


def test_ordinal_exact_order_and_negative_tolerance():
    config, data = configured()
    with pytest.raises(DomainError):
        validate_configuration(
            replace(config, criteria=(replace(config.criteria[0], tolerance=-1),)), data
        )
    ordinal = normalize_ratings(criterion([("low", "high")]), RatingType.ORDINAL)
    config = replace(
        config,
        criteria=(
            CriterionConfiguration("Quality", RatingType.ORDINAL, ordinal_order=("low", "high")),
        ),
    )
    assert validate_configuration(config, (ordinal,)) == config
    with pytest.raises(DomainError):
        validate_configuration(
            replace(config, criteria=(replace(config.criteria[0], ordinal_order=("low",)),)),
            (ordinal,),
        )
