"""Deterministic aligned workbook dataset with public aliases only."""

from dataclasses import dataclass, replace

from inter_rater_analyzer.domain import DomainError, ErrorCode
from inter_rater_analyzer.identity import Criterion, RaterMapping, normalize_criterion
from inter_rater_analyzer.ingestion import RawCriterion


@dataclass(frozen=True)
class WorkbookDataset:
    criteria: tuple[Criterion, ...]
    item_ids: tuple[str, ...]

    @property
    def item_count(self) -> int:
        return len(self.item_ids)

    @property
    def rater_count(self) -> int:
        return len(self.criteria[0].raters)

    @property
    def criterion_names(self) -> tuple[str, ...]:
        return tuple(criterion.name for criterion in self.criteria)

    def ratings(self, criterion_name: str, item_id: str) -> tuple[object, ...]:
        for criterion in self.criteria:
            if criterion.name == criterion_name:
                for row in criterion.rows:
                    if row.item_id == item_id:
                        return row.ratings
        raise KeyError((criterion_name, item_id))


def canonicalize(
    raw_criteria: tuple[RawCriterion, ...],
) -> tuple[WorkbookDataset, tuple[RaterMapping, ...]]:
    if not raw_criteria:
        raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Add a visible criterion worksheet.")
    normalized = tuple(normalize_criterion(raw) for raw in raw_criteria)
    first, mappings = normalized[0]
    item_ids = tuple(sorted(row.item_id for row in first.rows))
    identities = tuple(mapping.normalized for mapping in mappings)
    criteria: list[Criterion] = []
    for criterion, mapping in normalized:
        if tuple(sorted(row.item_id for row in criterion.rows)) != item_ids:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "All criteria must use the same Item IDs."
            )
        if tuple(rater.normalized for rater in mapping) != identities:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE,
                "All criteria must use the same raters in the same order.",
            )
        criteria.append(
            replace(criterion, rows=tuple(sorted(criterion.rows, key=lambda row: row.item_id)))
        )
    return WorkbookDataset(tuple(criteria), item_ids), mappings
