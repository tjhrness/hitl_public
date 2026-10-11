"""Service-backed public text projections for the fixed desktop navigation."""

from dataclasses import dataclass

from inter_rater_analyzer.config import APPLICATION_VERSION
from inter_rater_analyzer.services import Services

NAVIGATION = ("New Analysis", "Analysis History", "Presets", "Backup History", "Settings")


@dataclass(frozen=True)
class ShellPresenter:
    services: Services

    def page(self, index: int) -> str:
        if index == 0:
            state = self.services.drafts.active()
            return (
                "Resume Draft\nYour setup has been saved."
                if state
                else "New Analysis\nCreate an analysis from an Excel workbook."
            )
        if index == 1:
            history = self.services.history.list()
            return "Analysis History\n\n" + (
                "\n".join(
                    f"{h.name} · v{h.number} · {h.status} · {h.version_type}\n{h.change_note}"
                    for h in history
                )
                or "No analyses yet."
            )
        if index == 2:
            presets = self.services.presets.list()
            return "Presets\n\n" + (
                "\n".join(p.name for p in presets)
                or "No saved presets. You can configure an analysis manually."
            )
        if index == 3:
            backups = sorted(self.services.paths.backups.glob("*.irabackup"))
            return "Backup History\n\n" + ("\n".join(p.name for p in backups) or "No backups yet.")
        return (
            f"Settings\n\nApplication version {APPLICATION_VERSION}\n"
            f"Offline storage: {self.services.paths.root}\n"
            "One fixed theme. All analysis runs locally."
        )
