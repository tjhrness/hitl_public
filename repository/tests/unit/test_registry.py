import json
from dataclasses import asdict

import pytest

from inter_rater_analyzer.domain import DomainError, MetricScope, RatingType
from inter_rater_analyzer.metric_registry import MetricDefinition, MetricRegistry, MetricResult


def definition(identifier="test"):
    return MetricDefinition(
        identifier,
        "Test metric",
        (RatingType.NOMINAL,),
        MetricScope.OVERALL,
        True,
        ("complete ratings",),
        False,
        False,
        "test",
        "Test-only statistic",
        "1.0",
        lambda data, config: (),
        lambda data, config: (),
    )


def test_registry_filters_duplicates_and_selection():
    registry = MetricRegistry()
    registry.register(definition())
    assert registry.defaults(RatingType.NOMINAL) == ("test",)
    assert registry.applicable(RatingType.CONTINUOUS) == ()
    with pytest.raises(DomainError):
        registry.register(definition())
    with pytest.raises(DomainError):
        registry.validate_selection(("test", "test"), RatingType.NOMINAL)
    with pytest.raises(DomainError):
        registry.validate_selection(("test",), RatingType.ORDINAL)
    with pytest.raises(DomainError):
        registry.validate_selection(("unknown",), RatingType.NOMINAL)


def test_result_serialization_and_invalid_numbers():
    result = MetricResult("test", "Quality", 0.75, implementation_version="1.0")
    assert json.loads(json.dumps(asdict(result)))["estimate"] == 0.75
    assert "raw_p" not in asdict(result)
    for value in [float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            MetricResult("test", "Quality", value)
