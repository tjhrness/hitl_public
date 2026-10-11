"""Permanent named presets applied by rating type after workbook typing."""

import math
import sqlite3
from dataclasses import dataclass, replace

from inter_rater_analyzer.configuration import AnalysisConfiguration, CriterionConfiguration
from inter_rater_analyzer.database import Migration, transaction
from inter_rater_analyzer.domain import (
    AnalysisVersionId,
    DomainError,
    ErrorCode,
    PresetId,
    RatingType,
    ValidationSeverity,
    require_text,
)
from inter_rater_analyzer.drafts import DraftService, DraftState, decode, encode
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.ratings import NormalizedCriterion

PRESET_MIGRATION = Migration(
    7,
    (
        "CREATE TABLE presets(id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "name_key TEXT NOT NULL UNIQUE, "
        "payload TEXT NOT NULL, tolerance_fraction REAL NOT NULL CHECK(tolerance_fraction>=0))",
        "CREATE TRIGGER presets_immutable BEFORE UPDATE ON presets "
        "BEGIN SELECT RAISE(ABORT,'Presets are immutable'); END",
        "CREATE TRIGGER presets_permanent BEFORE DELETE ON presets "
        "BEGIN SELECT RAISE(ABORT,'Presets are permanent'); END",
    ),
)


@dataclass(frozen=True)
class Preset:
    id: PresetId
    name: str
    configuration: AnalysisConfiguration
    tolerance_fraction: float


@dataclass(frozen=True)
class PresetService:
    drafts: DraftService

    def create_from_version(
        self, name: str, identifier: AnalysisVersionId, *, tolerance_fraction: float = 0.05
    ) -> Preset:
        with self.drafts.database.connection() as conn:
            row = conn.execute(
                "SELECT d.payload FROM drafts d JOIN analysis_versions v "
                "ON v.id=d.version_id WHERE v.id=? AND v.status='Completed'",
                (str(identifier),),
            ).fetchone()
        if row is None:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Select a Completed version.")
        config = decode(identifier, row[0]).configuration
        if config is None:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "No configuration available.")
        return self.create(name, config, tolerance_fraction=tolerance_fraction)

    def create(
        self, name: str, configuration: AnalysisConfiguration, *, tolerance_fraction: float = 0.05
    ) -> Preset:
        require_text(name, "a preset name")
        if not math.isfinite(tolerance_fraction) or tolerance_fraction < 0:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Use a finite nonnegative range fraction."
            )
        by_type: dict[RatingType, tuple[str, ...]] = {}
        for criterion in configuration.criteria:
            get_registry().validate_selection(criterion.metrics, criterion.rating_type)
            if (
                criterion.rating_type in by_type
                and by_type[criterion.rating_type] != criterion.metrics
            ):
                raise DomainError(
                    ErrorCode.VALIDATION_VALUE,
                    "Preset metrics must be consistent within each rating type.",
                )
            by_type[criterion.rating_type] = criterion.metrics
        if (
            not configuration.criteria
            or not 0 < configuration.confidence < 100
            or not 0 < configuration.alpha < 1
        ):
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Use valid confidence, alpha and criteria."
            )
        if (
            not configuration.weights
            or len({w.signal for w in configuration.weights}) != len(configuration.weights)
            or any(not w.weight.is_finite() or w.weight < 0 for w in configuration.weights)
            or sum(w.weight for w in configuration.weights) != 100
        ):
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Preset weights must total 100%.")
        # Workbook-specific names, exclusions and numeric tolerances are not reusable settings.
        reusable = replace(
            configuration,
            exclusions=(),
            criteria=tuple(
                replace(c, name=c.rating_type.value, tolerance=0) for c in configuration.criteria
            ),
        )
        preset = Preset(PresetId.new(), name.strip(), reusable, tolerance_fraction)
        payload = encode(DraftState(AnalysisVersionId.new(), configuration=reusable))
        try:
            with self.drafts.database.connection() as conn, transaction(conn):
                conn.execute(
                    "INSERT INTO presets VALUES(?,?,?,?,?)",
                    (
                        str(preset.id),
                        preset.name,
                        preset.name.casefold(),
                        payload,
                        tolerance_fraction,
                    ),
                )
        except sqlite3.IntegrityError:
            raise DomainError(ErrorCode.VALIDATION_VALUE, "Preset name already exists.") from None
        return preset

    def list(self) -> tuple[Preset, ...]:
        with self.drafts.database.connection() as conn:
            rows = conn.execute("SELECT * FROM presets ORDER BY name_key,id").fetchall()
        results: list[Preset] = []
        for row in rows:
            configuration = decode(AnalysisVersionId.new(), row["payload"]).configuration
            if configuration is None:
                raise DomainError(ErrorCode.DB_FAILED, "Preset configuration is missing.")
            results.append(
                Preset(
                    PresetId.parse(row["id"]), row["name"], configuration, row["tolerance_fraction"]
                )
            )
        return tuple(results)

    def get(self, identifier: PresetId) -> Preset:
        for preset in self.list():
            if preset.id == identifier:
                return preset
        raise DomainError(ErrorCode.VALIDATION_VALUE, "Preset does not exist.")

    def select(self, identifier: PresetId | None) -> None:
        if identifier is not None:
            self.get(identifier)
        state = self.drafts.active()
        if state is None or state.workbook_id is not None:
            raise DomainError(
                ErrorCode.VALIDATION_VALUE, "Select a preset before uploading a workbook."
            )
        self.drafts.save(replace(state, preset_id=identifier))

    def apply(
        self, identifier: PresetId, data: tuple[NormalizedCriterion, ...]
    ) -> tuple[AnalysisConfiguration, tuple[ValidationFinding, ...]]:
        preset = self.get(identifier)
        results: list[CriterionConfiguration] = []
        warnings: list[ValidationFinding] = []
        for current in data:
            candidates = [
                c for c in preset.configuration.criteria if c.rating_type is current.rating_type
            ]
            warning = ""
            code = "PRESET_TYPE_SKIPPED"
            if not candidates:
                warning = "No saved settings for this rating type; configure it manually."
                selected = CriterionConfiguration(
                    current.name,
                    current.rating_type,
                    metrics=get_registry().defaults(current.rating_type),
                )
            else:
                selected = candidates[0]
                if current.rating_type is RatingType.ORDINAL:
                    matching = [
                        c
                        for c in candidates
                        if set(c.ordinal_order) == set(current.categories)
                        and len(c.ordinal_order) == len(current.categories)
                    ]
                    if matching:
                        selected = matching[0]
                    else:
                        selected = replace(selected, ordinal_order=())
                        code = "PRESET_ORDINAL_MISMATCH"
                        warning = "Saved ordinal labels do not match; confirm the order manually."
            numbers = (
                [float(v) for row in current.values for v in row]
                if current.rating_type is RatingType.CONTINUOUS
                else []
            )
            tolerance = preset.tolerance_fraction * (max(numbers) - min(numbers)) if numbers else 0
            results.append(replace(selected, name=current.name, tolerance=tolerance))
            if warning:
                warnings.append(
                    ValidationFinding(
                        code,
                        warning,
                        "Review criterion settings.",
                        ValidationSeverity.WARNING,
                        current.name,
                    )
                )
        absent = {c.rating_type for c in preset.configuration.criteria} - {
            d.rating_type for d in data
        }
        for kind in sorted(absent):
            warnings.append(
                ValidationFinding(
                    "PRESET_UNUSED_TYPE",
                    f"Unused {kind} preset settings skipped.",
                    "No action required.",
                    ValidationSeverity.WARNING,
                )
            )
        return replace(preset.configuration, criteria=tuple(results)), tuple(warnings)
