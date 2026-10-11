"""Common report projection and atomic immutable PDF/DOCX/PNG packages."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from inter_rater_analyzer.artifacts import atomic_write, sanitize_filename, sha256
from inter_rater_analyzer.comparison import ComparisonService
from inter_rater_analyzer.config import APPLICATION_VERSION, RuntimePaths
from inter_rater_analyzer.database import Migration, transaction
from inter_rater_analyzer.domain import AnalysisVersionId, DomainError, ErrorCode
from inter_rater_analyzer.execution import ExecutionService
from inter_rater_analyzer.history import HistoryService
from inter_rater_analyzer.metric_registry import get_registry
from inter_rater_analyzer.privacy import check_artifact, check_text

REPORT_MIGRATION = Migration(
    8,
    (
        "CREATE TABLE report_artifacts(version_id TEXT PRIMARY KEY "
        "REFERENCES analysis_versions(id), "
        "path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL)",
        "CREATE TRIGGER reports_immutable BEFORE UPDATE ON report_artifacts "
        "BEGIN SELECT RAISE(ABORT,'Reports are immutable'); END",
        "CREATE TRIGGER reports_permanent BEFORE DELETE ON report_artifacts "
        "BEGIN SELECT RAISE(ABORT,'Reports are permanent'); END",
    ),
)


@dataclass(frozen=True)
class ReportSection:
    title: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class ReportModel:
    title: str
    sections: tuple[ReportSection, ...]


@dataclass(frozen=True)
class ReportArtifact:
    path: Path
    sha256: str


def build_model(execution: ExecutionService, identifier: AnalysisVersionId) -> ReportModel:
    snapshot = execution.load(identifier)
    result = snapshot["result"]
    version = execution.drafts.analyses.get_version(identifier)
    history = next(
        h for h in HistoryService(execution.database).list() if h.version_id == identifier
    )
    sections = [
        ReportSection(
            "Metadata",
            (
                f"{history.name} version {history.number}. Application {APPLICATION_VERSION}.",
                "This report describes observed inter-rater agreement and items for human review. "
                "Interpret estimates with their uncertainty, measurement scale and study context.",
                f"Change note: {history.change_note or 'Initial analysis'}",
            ),
        ),
        ReportSection(
            "Executive summary", tuple(f"{s['message']} Why: {s['why']}" for s in result["summary"])
        ),
    ]
    sections.append(
        ReportSection(
            "Cross criteria summary",
            tuple(
                f"{c['name']}: {m['metric_id']} = {m['estimate']:.4g}"
                for c in result["criteria"]
                for m in c["metrics"]
                if not m["pair"]
            ),
        )
    )
    metrics: list[str] = []
    methods: list[str] = []
    caveats: list[str] = []
    for criterion in result["criteria"]:
        for metric in criterion["metrics"]:
            ci = metric["ci"]
            metrics.append(
                f"{criterion['name']} / {metric['metric_id']} / "
                f"{' and '.join(metric['pair'] or ())}: {metric['estimate']:.4g}; "
                f"CI {ci['lower']:.4g} to {ci['upper']:.4g} "
                f"({ci['confidence']:g}%, {ci['method']}); "
                "adjusted p="
                + str(metric["adjusted_p"] if metric["adjusted_p"] is not None else "N/A")
                + ". "
                f"{metric['interpretation']} {metric['convention']}"
            )
            methods.append(get_registry().get(metric["metric_id"]).methodology)
            caveats.extend(metric["warnings"])
    sections.append(ReportSection("Criterion results", tuple(metrics)))
    sections.append(
        ReportSection(
            "Rater diagnostics",
            tuple(
                f"{c['name']} / {r['alias']}: agreement {r['agreement']:.4g}%; "
                f"disagreement {r['disagreement']:.4g}%; "
                f"outlier frequency {r['outlier_frequency']:.4g}%; "
                f"category distribution {r['distribution']}; variance {r['variance']}; "
                f"spread {r['spread']}; signed direction {r['direction']}."
                for c in result["criteria"]
                for r in c["raters"]
            ),
        )
    )
    top = result["ranking"][0]
    sections.append(
        ReportSection(
            "Human review summary",
            (
                f"Highest-priority Item ID {top['item_id']}; score {top['score']}. "
                "The complete ranked list is available in the application.",
                *(
                    f"{c['criterion']}: score {c['score']}; "
                    + "; ".join(
                        f"{w['signal']} normalized {w['normalized']}, "
                        f"effective weight {w['effective_weight']}%, "
                        f"contribution {w['contribution']}"
                        for w in c["contributions"]
                    )
                    for c in top["criteria"]
                ),
            ),
        )
    )
    if version.number > 1:
        try:
            comparison = ComparisonService(execution).latest(identifier)
            changes = [
                f"Changed cells: {len(comparison.cells)}. Magnitudes: {comparison.magnitudes}."
            ]
            material = {(c.criterion, c.item_id) for c in comparison.consensus if c.material}
            totals: dict[tuple[str, str], float] = {}
            for cell in comparison.cells:
                key = (cell.criterion, cell.item_id)
                if key in material and cell.magnitude is not None:
                    totals[key] = totals.get(key, 0) + cell.magnitude
            # Round-robin criterion rankings avoid adding incompatible measurement units.
            candidates = [
                sorted(
                    (
                        (item, magnitude)
                        for (criterion, item), magnitude in totals.items()
                        if criterion == name
                    ),
                    key=lambda value: (-value[1], value[0]),
                )
                for name in sorted({key[0] for key in totals})
            ]
            chosen: list[str] = []
            for rank in range(max(map(len, candidates), default=0)):
                for group in candidates:
                    if rank < len(group) and group[rank][0] not in chosen and len(chosen) < 10:
                        chosen.append(group[rank][0])
            changes.append(
                "At most 10 distinct material Item IDs, selected round-robin from "
                "criterion rankings by descending type-specific magnitude; "
                "criterion names break cross-criterion ties."
            )
            changes += [
                f"{item}: "
                + "; ".join(
                    f"{name} magnitude {magnitude:g}"
                    for (name, candidate), magnitude in totals.items()
                    if candidate == item
                )
                for item in chosen
            ]
            changes += [
                f"Configuration {key}: {before} to {after}"
                for key, before, after in comparison.configuration_changes
            ]
            sections.append(ReportSection("Version comparison", tuple(changes)))
        except DomainError:
            sections.append(
                ReportSection(
                    "Version comparison",
                    (
                        "Immediately previous completed results are unavailable; "
                        "no comparison was computed.",
                    ),
                )
            )
    sections += [
        ReportSection("Methodology", tuple(dict.fromkeys(methods))),
        ReportSection(
            "Caveats", tuple(dict.fromkeys(caveats)) or ("No additional metric caveats.",)
        ),
        ReportSection(
            "Exclusions appendix",
            tuple(f"{e['item_id']}: {e['reason']}" for e in snapshot["configuration"]["exclusions"])
            or ("No excluded items.",),
        ),
        ReportSection(
            "Audit appendix",
            (
                f"Application {APPLICATION_VERSION}; version identifier {identifier}; "
                f"created {version.created_at.isoformat()}; completed {version.completed_at}.",
                f"Stable seed input digest: {snapshot['seed_key']}. "
                "Master seed 1729; BCa 10000 resamples.",
                "Seed scheme: sha256-json-utf8-first64-big-v1. Child keys: input digest, "
                "criterion name, metric ID, JSON rater pair. BCa implementation 1.1 treats "
                "numerical ties with relative tolerance 1e-12 and absolute tolerance 1e-14.",
                "Saved metric implementation versions: "
                + ", ".join(
                    sorted(
                        {
                            m["implementation_version"]
                            for c in result["criteria"]
                            for m in c["metrics"]
                        }
                    )
                ),
                "Configuration: " + json.dumps(snapshot["configuration"], ensure_ascii=False),
                "Static item heatmaps show at most 30 items with "
                "highest saved pairwise disagreement; "
                "ties use case-sensitive Item ID order. All Bland Altman pairs are included.",
            ),
        ),
    ]
    with execution.database.connection() as conn:
        source = conn.execute(
            "SELECT a.sha256 FROM execution_snapshots s "
            "JOIN workbook_artifacts a ON a.id=json_extract(s.payload,'$.workbook_id') "
            "WHERE s.version_id=?",
            (str(identifier),),
        ).fetchone()
    if source:
        audit = sections[-1]
        sections[-1] = ReportSection(
            audit.title, audit.paragraphs + (f"Workbook SHA256: {source[0]}",)
        )

    def readable(text: str) -> str:
        return re.sub(
            r"-?\d+\.\d{5,}(?:[Ee][+-]?\d+)?", lambda match: f"{float(match.group()):.4g}", text
        )

    return ReportModel(
        "Inter Rater Variability Analysis",
        tuple(
            section
            if section.title == "Audit appendix"
            else ReportSection(section.title, tuple(readable(text) for text in section.paragraphs))
            for section in sections
        ),
    )


def render_visuals(snapshot: dict[str, Any], directory: Path) -> tuple[Path, ...]:
    # Untyped plotting-library boundary is contained in this renderer.
    Figure = import_module("matplotlib.figure").Figure
    paths: list[Path] = []
    for index, criterion in enumerate(snapshot["result"]["criteria"]):
        items = sorted(
            criterion["signals"],
            key=lambda item: (-item["signals"][0]["normalized"], item["item_id"]),
        )[:30]
        figure = Figure(figsize=(7, max(2.5, len(items) * 0.22 + 1)))
        axis = figure.subplots()
        heat = axis.imshow(
            [
                [
                    s["normalized"] if s["normalized"] is not None else float("nan")
                    for s in item["signals"]
                ]
                for item in items
            ],
            vmin=0,
            vmax=100,
            cmap="YlOrRd",
            aspect="auto",
        )
        axis.set_yticks(range(len(items)), [item["item_id"][:24] for item in items])
        axis.set_xticks(
            range(6),
            ["Pairwise", "Inverse mode", "Spread", "Deviation", "Outlier", "No consensus"],
            rotation=35,
        )
        axis.set_title(f"{criterion['name']} disagreement signals")
        figure.colorbar(heat, ax=axis, label="Normalized signal (0 to 100)")
        path = directory / f"criterion_{index + 1}_items.png"
        figure.savefig(str(path), dpi=160, bbox_inches="tight")
        paths.append(path)
        for pair_index, metric in enumerate(criterion["metrics"]):
            ba = metric["bland_altman"]
            if ba is None:
                continue
            figure = Figure(figsize=(7, 4))
            axis = figure.subplots()
            axis.scatter(ba["means"], ba["differences"], s=12, alpha=0.7)
            for level in (metric["estimate"], ba["lower"], ba["upper"]):
                axis.axhline(level, linestyle="--")
            axis.set_xlabel("Pair mean")
            axis.set_ylabel("First rater minus second")
            axis.set_title(f"{criterion['name']}: {' / '.join(metric['pair'])}")
            path = directory / f"criterion_{index + 1}_ba_{pair_index}.png"
            figure.savefig(str(path), dpi=160, bbox_inches="tight")
            paths.append(path)
    return tuple(paths)


def render_documents(model: ReportModel, visuals: tuple[Path, ...], directory: Path) -> None:
    # Typed ReportModel is the boundary for libraries without complete type stubs.
    docx = import_module("docx")
    shared = import_module("docx.shared")
    document = docx.Document()
    section = document.sections[0]
    section.page_width, section.page_height = shared.Inches(8.5), shared.Inches(11)
    section.top_margin = section.bottom_margin = shared.Inches(0.75)
    section.left_margin = section.right_margin = shared.Inches(0.8)
    document.styles["Normal"].font.name = "Arial"
    document.styles["Normal"].font.size = shared.Pt(11)
    document.styles["Normal"].paragraph_format.space_after = shared.Pt(6)
    document.styles["Normal"].paragraph_format.line_spacing = 1.05
    for name in ("Title", "Heading 1"):
        style = document.styles[name]
        style.font.color.rgb = shared.RGBColor(0, 0, 0)
        style.paragraph_format.space_before = shared.Pt(12)
        style.paragraph_format.space_after = shared.Pt(6)
        for border in style.element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    document.add_paragraph(model.title, "Title")
    platypus = import_module("reportlab.platypus")
    styles = import_module("reportlab.lib.styles").getSampleStyleSheet()
    font_path = import_module("matplotlib.font_manager").findfont("DejaVu Sans")
    import_module("reportlab.pdfbase.pdfmetrics").registerFont(
        import_module("reportlab.pdfbase.ttfonts").TTFont("ReportSans", font_path)
    )
    for name in ("Normal", "Title", "Heading1"):
        styles[name].fontName = "ReportSans"
    styles["Normal"].fontSize, styles["Normal"].leading = 10, 14
    styles["Heading1"].keepWithNext = True
    story: list[Any] = [platypus.Paragraph(escape(model.title), styles["Title"])]
    for content in model.sections:
        document.add_heading(content.title, 1)
        story.append(platypus.Paragraph(escape(content.title), styles["Heading1"]))
        for paragraph in content.paragraphs:
            document.add_paragraph(paragraph)
            story += [
                platypus.Paragraph(escape(paragraph), styles["Normal"]),
                platypus.Spacer(1, 7),
            ]
    document.add_heading("Visual diagnostics", 1)
    story.append(platypus.Paragraph("Visual diagnostics", styles["Heading1"]))
    for path in visuals:
        document.add_picture(str(path), width=shared.Inches(6))
        image = platypus.Image(str(path))
        factor = min(400 / image.imageWidth, 560 / image.imageHeight)
        image.drawWidth, image.drawHeight = image.imageWidth * factor, image.imageHeight * factor
        story.append(image)
    document.save(str(directory / "report.docx"))
    platypus.SimpleDocTemplate(
        str(directory / "report.pdf"),
        pagesize=(612, 792),
        leftMargin=57.6,
        rightMargin=57.6,
        topMargin=54,
        bottomMargin=54,
    ).build(story)


@dataclass(frozen=True)
class ReportService:
    execution: ExecutionService
    paths: RuntimePaths

    def generate(self, identifier: AnalysisVersionId) -> ReportArtifact:
        snapshot = self.execution.load(identifier)
        model = build_model(self.execution, identifier)
        history = next(
            h for h in HistoryService(self.execution.database).list() if h.version_id == identifier
        )
        filename = (
            f"{sanitize_filename(history.name)}_v{history.number}_{datetime.now():%Y-%m-%d}.zip"
        )
        target = self.paths.reports / str(identifier) / filename
        written = False
        try:
            with self.execution.database.connection() as conn, transaction(conn):
                if conn.execute(
                    "SELECT 1 FROM report_artifacts WHERE version_id=?", (str(identifier),)
                ).fetchone():
                    raise DomainError(
                        ErrorCode.REPORT_FAILED, "This version already has an immutable report."
                    )
                with TemporaryDirectory(dir=self.paths.temp) as temporary:
                    identities = tuple(
                        row[0]
                        for row in conn.execute(
                            "SELECT original FROM rater_mappings WHERE analysis_id="
                            "(SELECT analysis_id FROM analysis_versions WHERE id=?)",
                            (str(identifier),),
                        )
                    )
                    check_text(json.dumps(asdict(model)), identities)
                    check_text(json.dumps(snapshot), identities)
                    directory = Path(temporary)
                    visuals = render_visuals(snapshot, directory)
                    render_documents(model, visuals, directory)
                    if not (directory / "report.pdf").read_bytes().startswith(b"%PDF"):
                        raise ValueError("Invalid PDF")
                    with ZipFile(directory / "report.docx") as document:
                        content = document.read("word/document.xml")
                        if b"Audit appendix" not in content:
                            raise ValueError("Incomplete DOCX")
                    package = directory / "package.zip"
                    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
                        for path in (directory / "report.pdf", directory / "report.docx", *visuals):
                            archive.write(path, path.name)
                    payload = package.read_bytes()
                    check_artifact(filename, payload, identities)
                    digest = sha256(payload)
                    atomic_write(target, payload)
                    written = True
                    conn.execute(
                        "INSERT INTO report_artifacts VALUES(?,?,?)",
                        (str(identifier), target.relative_to(self.paths.root).as_posix(), digest),
                    )
            return ReportArtifact(target, digest)
        except Exception:
            if written:
                target.unlink(missing_ok=True)
            raise DomainError(
                ErrorCode.REPORT_FAILED,
                "Report generation failed or a report already exists; no new package was saved.",
            ) from None
