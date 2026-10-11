"""Explicit rating-type normalization; never infer the user's measurement level."""

import math
import re
from dataclasses import dataclass

from inter_rater_analyzer.domain import RatingType
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.identity import Criterion

type Rating = str | float
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def normalize_value(value: object, kind: RatingType) -> Rating:
    if isinstance(value, bool) or value is None:
        raise ValueError("Not a rating")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Not finite")
        return number
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Not a rating")
    text = value.strip().casefold()
    if kind in (RatingType.ORDINAL, RatingType.CONTINUOUS) and NUMBER.fullmatch(text):
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("Not finite")
        return number
    if kind is RatingType.CONTINUOUS:
        raise ValueError("Not numeric")
    return text


def category_key(value: Rating) -> tuple[int, float, str]:
    return (1, 0.0, value) if isinstance(value, str) else (0, float(value), "")


@dataclass(frozen=True)
class NormalizedCriterion:
    name: str
    rating_type: RatingType
    item_ids: tuple[str, ...]
    raters: tuple[str, ...]
    values: tuple[tuple[Rating, ...], ...]
    categories: tuple[Rating, ...]
    minimum: float | None
    maximum: float | None
    findings: tuple[ValidationFinding, ...] = ()


def normalize_ratings(criterion: Criterion, kind: RatingType) -> NormalizedCriterion:
    findings: list[ValidationFinding] = []
    rows: list[tuple[Rating, ...]] = []
    for row in criterion.rows:
        normalized: list[Rating] = []
        for value in row.ratings:
            try:
                normalized.append(normalize_value(value, kind))
            except ValueError, OverflowError:
                findings.append(
                    ValidationFinding(
                        "VALIDATION_RATING_TYPE",
                        "A rating is incompatible with the selected type.",
                        "Enter a finite numeric value or a valid category for the selected type.",
                        worksheet=criterion.name,
                        item_id=row.item_id,
                        row=row.excel_row,
                    )
                )
        rows.append(tuple(normalized))
    flattened = [value for row in rows for value in row]
    categories = tuple(sorted(set(flattened), key=category_key))
    if kind is RatingType.BINARY and len(categories) > 2:
        findings.append(
            ValidationFinding(
                "VALIDATION_BINARY_CATEGORIES",
                "Binary data has more than two categories.",
                "Use at most two normalized categories.",
                worksheet=criterion.name,
            )
        )
    numbers = [value for value in flattened if isinstance(value, float)]
    continuous = kind is RatingType.CONTINUOUS
    return NormalizedCriterion(
        criterion.name,
        kind,
        tuple(row.item_id for row in criterion.rows),
        criterion.raters,
        tuple(rows) if not findings else (),
        () if continuous else categories,
        min(numbers) if continuous and numbers else None,
        max(numbers) if continuous and numbers else None,
        tuple(findings),
    )
