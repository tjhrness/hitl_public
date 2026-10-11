"""Virtualized read-only dashboard; statistical projections live outside widgets."""

from functools import partial

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableView,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from inter_rater_analyzer.domain import AnalysisVersionId
from inter_rater_analyzer.results_presenter import ResultsPresenter
from inter_rater_analyzer.services import Services

ROOT_INDEX = QModelIndex()


class ReadOnlyModel(QAbstractTableModel):
    def __init__(
        self, headers: tuple[str, ...], rows: tuple[tuple[object, ...], ...], *, heat: bool = False
    ) -> None:
        super().__init__()
        self.headers, self.rows, self.heat = headers, rows, heat

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "N/A"
                if value is None
                else f"{value:.4g}"
                if isinstance(value, float)
                else str(value)
            )
        if role == Qt.ItemDataRole.BackgroundRole and self.heat and isinstance(value, (int, float)):
            return QColor.fromHsvF(0.55, min(1, max(0, float(value) / 100)) * 0.65, 0.97)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None


def table(
    headers: tuple[str, ...], rows: tuple[tuple[object, ...], ...], *, heat: bool = False
) -> QTableView:
    view = QTableView()
    model = ReadOnlyModel(headers, rows, heat=heat)
    model.setParent(view)
    view.setModel(model)
    view.setAlternatingRowColors(not heat)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    view.horizontalHeader().setStretchLastSection(True)
    return view


def text_page(text: str) -> QTextBrowser:
    widget = QTextBrowser()
    widget.setPlainText(text)
    return widget


class ResultsDashboard(QWidget):
    def __init__(self, services: Services, identifier: AnalysisVersionId) -> None:
        super().__init__()
        self.presenter = ResultsPresenter(services, identifier)
        snapshot = self.presenter.snapshot()
        result = snapshot["result"]
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(
            text_page(
                "\n\n".join(
                    f"{entry['message']}\nWhy: {entry['why']}" for entry in result["summary"]
                )
            ),
            "Executive Summary",
        )
        self.tabs.addTab(
            table(
                ("Criterion", "Metric", "Estimate"),
                tuple(
                    (criterion["name"], metric["metric_id"], metric["estimate"])
                    for criterion in result["criteria"]
                    for metric in criterion["metrics"]
                    if not metric["pair"]
                ),
            ),
            "Cross-Criteria Comparison",
        )
        criterion_tabs = QTabWidget()
        self.tabs.addTab(criterion_tabs, "Criterion Details")
        for criterion in result["criteria"]:
            sections = QTabWidget()
            criterion_tabs.addTab(sections, criterion["name"])
            sections.addTab(
                table(
                    ("Metric", "Pair", "Estimate", "Confidence interval", "Adjusted p"),
                    tuple(
                        (
                            m["metric_id"],
                            " / ".join(m["pair"] or ()),
                            m["estimate"],
                            f"{m['ci']['lower']:.4g} – {m['ci']['upper']:.4g}" if m["ci"] else None,
                            m["adjusted_p"],
                        )
                        for m in criterion["metrics"]
                    ),
                ),
                "Key metrics",
            )
            sections.addTab(
                text_page(
                    "\n\n".join(
                        f"{m['metric_id']}: {m['interpretation']}\n{m['convention']}\n"
                        + "\n".join(m["warnings"])
                        for m in criterion["metrics"]
                    )
                ),
                "Interpretation / warnings",
            )
            headers, rows = self.presenter.pairwise(criterion["name"])
            sections.addTab(table(headers, rows, heat=True), "Pairwise agreement heatmap")
            signals = criterion["signals"]
            signal_headers = tuple(s["signal"] for s in signals[0]["signals"]) if signals else ()
            sections.addTab(
                table(
                    ("Item ID", *signal_headers),
                    tuple(
                        (item["item_id"], *(s["normalized"] for s in item["signals"]))
                        for item in signals
                    ),
                    heat=True,
                ),
                "Item disagreement heatmap",
            )
            sections.addTab(
                table(
                    ("Rater", "Category use", "Variance", "Spread", "Direction"),
                    tuple(
                        (r["alias"], r["distribution"], r["variance"], r["spread"], r["direction"])
                        for r in criterion["raters"]
                    ),
                ),
                "Category / continuous diagnostics",
            )
            drill = table(
                ("Item ID", "Consensus", "Ratings", "Outliers"),
                tuple(
                    (
                        i["item_id"],
                        i["consensus"] if i["consensus"] is not None else "No consensus",
                        i["ratings"],
                        i["outliers"],
                    )
                    for i in criterion["items"]
                ),
            )
            drill.clicked.connect(
                partial(self.select_item, tuple(item["item_id"] for item in criterion["items"]))
            )
            sections.addTab(drill, "Drill-down")
        self.tabs.addTab(
            table(
                ("Criterion", "Rater", "Agreement %", "Disagreement %", "Outlier %"),
                tuple(
                    (
                        c["name"],
                        r["alias"],
                        r["agreement"],
                        r["disagreement"],
                        r["outlier_frequency"],
                    )
                    for c in result["criteria"]
                    for r in c["raters"]
                ),
            ),
            "Rater Diagnostics",
        )
        priority = QWidget()
        priority_layout = QVBoxLayout(priority)
        self.ranking = table(
            ("Rank", "Item ID", "Priority"),
            tuple((p["rank"], p["item_id"], p["score"]) for p in result["ranking"]),
        )
        self.ranking.clicked.connect(
            partial(self.select_item, tuple(item["item_id"] for item in result["ranking"]))
        )
        priority_layout.addWidget(self.ranking)
        self.detail = QTextBrowser()
        priority_layout.addWidget(self.detail)
        self.tabs.addTab(priority, "Human-Review Priority List")
        comparison = self.presenter.comparison_text()
        if comparison is not None:
            self.tabs.addTab(text_page(comparison), "Version Comparison")
        self.help_button = QPushButton("What does this mean?")
        self.help_button.clicked.connect(self.show_help)
        layout.addWidget(self.help_button)
        self.help_window: QTextBrowser | None = None

    def show_item(self, item_id: str) -> None:
        self.detail.setPlainText(self.presenter.item_text(item_id))
        self.tabs.setCurrentIndex(4)

    def select_item(self, identifiers: tuple[str, ...], index: QModelIndex) -> None:
        self.show_item(identifiers[index.row()])

    def show_help(self) -> None:
        self.help_window = text_page(self.presenter.help_text())
        self.help_window.setWindowTitle("What does this mean?")
        self.help_window.resize(760, 620)
        self.help_window.show()
