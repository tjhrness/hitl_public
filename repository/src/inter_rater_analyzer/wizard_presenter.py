"""Draft setup operations shared by the Qt wizard and headless callers."""

from dataclasses import dataclass, replace

from inter_rater_analyzer.configuration import (
    AnalysisConfiguration,
    CriterionConfiguration,
    recommended_tolerance,
    validate_configuration,
)
from inter_rater_analyzer.continuous import exclude_items
from inter_rater_analyzer.data_quality import quality_warnings
from inter_rater_analyzer.domain import DomainError, ErrorCode, RatingType, ValidationSeverity
from inter_rater_analyzer.findings import ValidationFinding
from inter_rater_analyzer.ratings import NormalizedCriterion
from inter_rater_analyzer.services import Services


@dataclass(frozen=True)
class WizardPresenter:
    services: Services

    def confirm_types(
        self, types: dict[str, RatingType]
    ) -> tuple[
        AnalysisConfiguration, tuple[NormalizedCriterion, ...], tuple[ValidationFinding, ...]
    ]:
        state = self.services.drafts.active()
        imported = self.services.drafts.resume_workbook()
        if state is None or imported is None:
            raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Import a workbook first.")
        data = imported.assign_types(types)
        findings = tuple(f for d in data for f in d.findings)
        if any(f.severity is ValidationSeverity.ERROR for f in findings):
            raise DomainError(ErrorCode.VALIDATION_VALUE, "\n".join(f.message for f in findings))
        if state.types_locked and state.configuration:
            return state.configuration, data, findings
        config = AnalysisConfiguration(
            tuple(
                CriterionConfiguration(
                    d.name,
                    d.rating_type,
                    tolerance=recommended_tolerance(d),
                    metrics=self.services.metrics.defaults(d.rating_type),
                )
                for d in data
            )
        )
        if state.preset_id:
            config, warnings = self.services.presets.apply(state.preset_id, data)
            findings += warnings
        self.services.drafts.save(replace(state, configuration=config, types_locked=True))
        return config, data, findings

    def save(
        self, config: AnalysisConfiguration, acknowledged: bool, *, validate: bool = False
    ) -> tuple[ValidationFinding, ...]:
        state = self.services.drafts.active()
        imported = self.services.drafts.resume_workbook()
        if state is None or imported is None:
            raise DomainError(ErrorCode.VALIDATION_REQUIRED, "Create and import a Draft first.")
        data = imported.assign_types({c.name: c.rating_type for c in config.criteria})
        if validate:
            validate_configuration(config, data)
        excluded = {e.item_id for e in config.exclusions}
        warnings = tuple(
            w
            for d in data
            for w in quality_warnings(replace(exclude_items(d, excluded), findings=()))
        )
        self.services.drafts.save(
            replace(
                state,
                configuration=config,
                acknowledged_warnings=tuple(sorted({w.code for w in warnings}))
                if acknowledged
                else (),
            )
        )
        return warnings
