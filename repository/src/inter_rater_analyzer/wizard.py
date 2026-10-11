"""Autosaved Qt analysis workflow with explicit review and background execution."""

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from inter_rater_analyzer.configuration import (
    AnalysisConfiguration,
    CriterionConfiguration,
    Exclusion,
    PrioritySignal,
    SignalWeight,
)
from inter_rater_analyzer.domain import DomainError, PresetId, RatingType
from inter_rater_analyzer.ratings import NormalizedCriterion, Rating
from inter_rater_analyzer.services import Services
from inter_rater_analyzer.wizard_presenter import WizardPresenter


class TaskThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    stage = Signal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget) -> None:
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except DomainError as error:
            self.failed.emit(error.message)
        except Exception:
            self.failed.emit("Operation failed. Check the workbook and local storage.")


def spin(value: float, maximum: float = 100) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(6)
    widget.setRange(0, maximum)
    widget.setValue(value)
    return widget


class AnalysisWizard(QWidget):
    task_done = Signal()
    completed = Signal(object)

    def __init__(self, services: Services) -> None:
        super().__init__()
        self.presenter = WizardPresenter(services)
        self.config: AnalysisConfiguration | None = None
        self.data: tuple[NormalizedCriterion, ...] = ()
        self.worker: TaskThread | None = None
        self.loading = True
        self.type_boxes: dict[str, QComboBox] = {}
        self.metric_checks: dict[str, dict[str, QCheckBox]] = {}
        self.orders: dict[str, QListWidget] = {}
        self.tolerances: dict[str, QDoubleSpinBox] = {}
        self.preview_tables: list[QTableWidget] = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.autosave)
        layout = QVBoxLayout(self)
        self.heading = QLabel("New Analysis")
        layout.addWidget(self.heading)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.progress = QLabel("Ready")
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        setup = QWidget()
        form = QFormLayout(setup)
        self.name = QLineEdit()
        self.description = QLineEdit()
        self.preset = QComboBox()
        self.preset.addItem("Manual configuration", None)
        for preset in services.presets.list():
            self.preset.addItem(preset.name, str(preset.id))
        form.addRow("Analysis name", self.name)
        form.addRow("Description", self.description)
        form.addRow("Preset", self.preset)
        self.start_button = QPushButton("Create Draft")
        self.start_button.clicked.connect(self.start_draft)
        form.addRow(self.start_button)
        self.import_button = QPushButton("Choose Excel workbook")
        self.import_button.clicked.connect(self.choose_workbook)
        form.addRow(self.import_button)
        self.tabs.addTab(setup, "1 · Setup")
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        self.preview = QTabWidget()
        preview_layout.addWidget(self.preview)
        self.confirm_button = QPushButton("Confirm and lock rating types")
        self.confirm_button.clicked.connect(self.confirm_types)
        preview_layout.addWidget(self.confirm_button)
        self.tabs.addTab(preview, "2 · Preview & types")
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        self.criteria = QTabWidget()
        settings_layout.addWidget(self.criteria)
        global_form = QFormLayout()
        self.confidence = spin(95)
        self.alpha = spin(0.05, 1)
        global_form.addRow("Confidence (%)", self.confidence)
        global_form.addRow("Significance alpha", self.alpha)
        settings_layout.addLayout(global_form)
        self.exclusions = QTableWidget(0, 3)
        self.exclusions.setHorizontalHeaderLabels(["Exclude", "Item ID", "Reason"])
        self.exclusions.setMaximumHeight(180)
        settings_layout.addWidget(self.exclusions)
        weights_form = QFormLayout()
        self.weights = {signal: spin(0) for signal in PrioritySignal}
        for signal, weight in self.weights.items():
            weights_form.addRow(signal.value.replace("_", " ").title() + " (%)", weight)
            weight.valueChanged.connect(self.changed)
        settings_layout.addLayout(weights_form)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        settings_layout.addWidget(self.warnings)
        self.acknowledge = QCheckBox("I acknowledge the displayed data-quality warnings")
        settings_layout.addWidget(self.acknowledge)
        review_button = QPushButton("Save and review")
        review_button.clicked.connect(self.prepare_review)
        settings_layout.addWidget(review_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings)
        self.tabs.addTab(scroll, "3 · Configure")
        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        self.review = QTextBrowser()
        review_layout.addWidget(self.review)
        self.execute_button = QPushButton("Execute analysis")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self.execute)
        review_layout.addWidget(self.execute_button)
        self.tabs.addTab(review_page, "4 · Review & execute")
        self.confidence.valueChanged.connect(self.changed)
        self.alpha.valueChanged.connect(self.changed)
        self.exclusions.itemChanged.connect(self.changed)
        state = services.drafts.active()
        if state:
            self.heading.setText("Resume Draft")
            entry = next(h for h in services.history.list() if h.version_id == state.version_id)
            self.name.setText(entry.name)
            self.name.setEnabled(False)
            self.description.setEnabled(False)
            self.start_button.setEnabled(False)
            self.preset.setEnabled(False)
            if state.workbook_id:
                self.populate_preview()
                if state.types_locked and state.configuration:
                    self.config, self.data, _ = self.presenter.confirm_types(
                        {c.name: c.rating_type for c in state.configuration.criteria}
                    )
                    self.populate_configuration()
        self.loading = False

    def toPlainText(self) -> str:
        return self.heading.text()

    def start_draft(self) -> None:
        try:
            self.presenter.services.drafts.create(self.name.text(), self.description.text())
            selected = self.preset.currentData()
            self.presenter.services.presets.select(PresetId.parse(selected) if selected else None)
            self.config = None
            self.data = ()
            self.preview.clear()
            self.criteria.clear()
            self.review.clear()
            self.import_button.setEnabled(True)
            self.confirm_button.setEnabled(True)
            self.execute_button.setEnabled(False)
            self.start_button.setEnabled(False)
            self.name.setEnabled(False)
            self.description.setEnabled(False)
            self.preset.setEnabled(False)
            self.progress.setText("Draft created. Choose a workbook.")
        except DomainError as error:
            self.progress.setText(error.message)

    def choose_workbook(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose workbook", "", "Excel (*.xlsx)")
        if filename:
            self.import_path(Path(filename))

    def launch(self, operation: Callable[[], object], done: Callable[[object], None]) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.tabs.setEnabled(False)
        worker = TaskThread(operation, self)
        self.worker = worker
        worker.stage.connect(self.progress.setText)
        worker.succeeded.connect(done)
        worker.failed.connect(self.failed)
        worker.finished.connect(self.finished)
        worker.start()

    def finished(self) -> None:
        self.tabs.setEnabled(True)
        self.task_done.emit()

    def failed(self, message: str) -> None:
        self.progress.setText(message)
        self.execute_button.setEnabled(False)
        self.tabs.setCurrentIndex(2)
        if self.presenter.services.drafts.active() is None:
            self.enable_new_setup()

    def enable_new_setup(self) -> None:
        self.start_button.setEnabled(True)
        self.name.setEnabled(True)
        self.description.setEnabled(True)
        self.preset.setEnabled(True)

    def import_path(self, path: Path) -> None:
        self.progress.setText("Importing and validating workbook")
        self.launch(
            lambda: self.presenter.services.drafts.attach_workbook(path),
            lambda _: self.populate_preview(),
        )

    def populate_preview(self) -> None:
        imported = self.presenter.services.drafts.resume_workbook()
        if imported is None:
            return
        if imported.findings:
            self.progress.setText("\n".join(f.message for f in imported.findings))
            return
        self.preview.clear()
        self.type_boxes.clear()
        self.preview_tables.clear()
        state = self.presenter.services.drafts.active()
        configured = (
            {c.name: c.rating_type for c in state.configuration.criteria}
            if state and state.configuration
            else {}
        )
        for criterion in imported.criteria:
            page = QWidget()
            form = QVBoxLayout(page)
            form.addWidget(
                QLabel(
                    f"{len(criterion.rows)} items · {len(criterion.raters)} raters · first 10 rows"
                )
            )
            table = QTableWidget(min(10, len(criterion.rows)), len(criterion.raters) + 1)
            table.setHorizontalHeaderLabels(["Item ID", *criterion.raters])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            for row_index, row in enumerate(criterion.rows[:10]):
                for column, value in enumerate((row.item_id, *row.ratings)):
                    table.setItem(row_index, column, QTableWidgetItem(str(value)))
            form.addWidget(table)
            types = QComboBox()
            types.addItems([kind.value for kind in RatingType])
            types.setCurrentText(configured.get(criterion.name, RatingType.NOMINAL).value)
            types.setEnabled(not bool(state and state.types_locked))
            form.addWidget(types)
            self.type_boxes[criterion.name] = types
            self.preview_tables.append(table)
            self.preview.addTab(page, criterion.name)
        self.confirm_button.setEnabled(not bool(state and state.types_locked))
        self.import_button.setEnabled(not bool(state and state.types_locked))
        self.tabs.setCurrentIndex(1)
        self.progress.setText("Review anonymized ratings and select each rating type.")

    def confirm_types(self) -> None:
        try:
            self.config, self.data, findings = self.presenter.confirm_types(
                {name: RatingType(box.currentText()) for name, box in self.type_boxes.items()}
            )
            self.populate_configuration()
            for box in self.type_boxes.values():
                box.setEnabled(False)
            self.confirm_button.setEnabled(False)
            self.import_button.setEnabled(False)
            self.warnings.setText("\n".join(f.message for f in findings))
        except DomainError as error:
            self.progress.setText(error.message)

    def populate_configuration(self) -> None:
        config = self.config
        if config is None:
            return
        self.loading = True
        self.criteria.clear()
        self.metric_checks.clear()
        self.orders.clear()
        self.tolerances.clear()
        for current, settings in zip(self.data, config.criteria, strict=True):
            settings = next(c for c in config.criteria if c.name == current.name)
            page = QWidget()
            form = QVBoxLayout(page)
            checks: dict[str, QCheckBox] = {}
            for metric in self.presenter.services.metrics.applicable(current.rating_type):
                check = QCheckBox(metric.name + (" (recommended)" if metric.recommended else ""))
                check.setToolTip(metric.methodology)
                check.setChecked(metric.id in settings.metrics)
                if metric.id == "raw_agreement" and current.rating_type in (
                    RatingType.BINARY,
                    RatingType.NOMINAL,
                ):
                    check.setChecked(True)
                    check.setEnabled(False)
                check.toggled.connect(self.changed)
                checks[metric.id] = check
                form.addWidget(check)
            self.metric_checks[current.name] = checks
            if current.rating_type is RatingType.ORDINAL:
                form.addWidget(
                    QLabel("Drag categories into ascending order, then confirm at review.")
                )
                order = QListWidget()
                order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
                for category in settings.ordinal_order or current.categories:
                    item = QListWidgetItem(str(category))
                    item.setData(Qt.ItemDataRole.UserRole, category)
                    order.addItem(item)
                order.model().rowsMoved.connect(self.changed)
                self.orders[current.name] = order
                form.addWidget(order)
            if current.rating_type is RatingType.CONTINUOUS:
                form.addWidget(
                    QLabel("Practical agreement tolerance (initial recommendation: 5% of range)")
                )
                tolerance = spin(settings.tolerance, 1e100)
                tolerance.valueChanged.connect(self.changed)
                self.tolerances[current.name] = tolerance
                form.addWidget(tolerance)
            self.criteria.addTab(page, current.name)
        self.confidence.setValue(config.confidence)
        self.alpha.setValue(config.alpha)
        weights = {w.signal: float(w.weight) for w in config.weights}
        for signal, widget in self.weights.items():
            widget.setValue(weights.get(signal, 0))
        excluded = {e.item_id: e.reason for e in config.exclusions}
        ids = self.data[0].item_ids
        self.exclusions.setRowCount(len(ids))
        for index, item_id in enumerate(ids):
            check = QTableWidgetItem()
            check.setCheckState(
                Qt.CheckState.Checked if item_id in excluded else Qt.CheckState.Unchecked
            )
            self.exclusions.setItem(index, 0, check)
            label = QTableWidgetItem(item_id)
            label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.exclusions.setItem(index, 1, label)
            self.exclusions.setItem(index, 2, QTableWidgetItem(excluded.get(item_id, "")))
        self.loading = False
        self.tabs.setCurrentIndex(2)

    def configuration(self) -> AnalysisConfiguration:
        assert self.config is not None
        criteria: list[CriterionConfiguration] = []
        for settings in self.config.criteria:
            order: tuple[Rating, ...] = settings.ordinal_order
            if settings.name in self.orders:
                widget = self.orders[settings.name]
                values: list[Rating] = []
                for index in range(widget.count()):
                    item = widget.item(index)
                    assert item is not None
                    values.append(item.data(Qt.ItemDataRole.UserRole))
                order = tuple(values)
            tolerance = self.tolerances.get(settings.name)
            criteria.append(
                replace(
                    settings,
                    ordinal_order=order,
                    tolerance=tolerance.value() if tolerance else settings.tolerance,
                    metrics=tuple(
                        key
                        for key, check in self.metric_checks[settings.name].items()
                        if check.isChecked()
                    ),
                )
            )
        exclusions: list[Exclusion] = []
        for row in range(self.exclusions.rowCount()):
            check, item, reason = (self.exclusions.item(row, col) for col in range(3))
            assert check is not None and item is not None and reason is not None
            if check.checkState() == Qt.CheckState.Checked:
                exclusions.append(Exclusion(item.text(), reason.text()))
        return replace(
            self.config,
            criteria=tuple(criteria),
            confidence=self.confidence.value(),
            alpha=self.alpha.value(),
            exclusions=tuple(exclusions),
            weights=tuple(
                SignalWeight(signal, Decimal(widget.text().replace(",", ".")))
                for signal, widget in self.weights.items()
                if widget.value() > 0
            ),
        )

    def changed(self, *_: object) -> None:
        if not self.loading:
            self.execute_button.setEnabled(False)
            self.acknowledge.setChecked(False)
            self.timer.start(300)

    def autosave(self) -> None:
        if self.config is not None and self.presenter.services.drafts.active():
            try:
                self.presenter.save(self.configuration(), False)
                self.progress.setText("Draft saved")
            except DomainError as error:
                self.progress.setText(error.message)

    def prepare_review(self) -> None:
        self.timer.stop()
        try:
            config = self.configuration()
            warnings = self.presenter.save(config, self.acknowledge.isChecked(), validate=True)
            self.warnings.setText("\n".join(w.message for w in warnings))
            if warnings and not self.acknowledge.isChecked():
                self.progress.setText("Acknowledge the displayed warnings before review.")
                return
            lines = [
                f"Confidence: {config.confidence:g}% · Alpha: {config.alpha:g}",
                f"Excluded items: {len(config.exclusions)}",
            ]
            for criterion in config.criteria:
                lines += [
                    f"\n{criterion.name} · {criterion.rating_type}",
                    "Metrics: " + ", ".join(criterion.metrics),
                    f"Ordinal order: {criterion.ordinal_order}",
                    f"Tolerance: {criterion.tolerance:g}",
                ]
            lines += [f"{w.signal.value}: {w.weight}%" for w in config.weights]
            lines += [f"Exclude {e.item_id}: {e.reason}" for e in config.exclusions]
            self.review.setPlainText("\n".join(lines))
            self.execute_button.setEnabled(True)
            self.tabs.setCurrentIndex(3)
        except (DomainError, ValueError) as error:
            self.progress.setText(str(error))

    def execute(self) -> None:
        if not self.execute_button.isEnabled():
            return
        state = self.presenter.services.drafts.active()
        if state is None:
            return
        self.timer.stop()
        self.execute_button.setEnabled(False)
        self.progress.setText("Validating and checking selected metrics")

        def operation() -> object:
            assert self.worker is not None
            return self.presenter.services.execution.execute(
                state.version_id, progress=self.worker.stage.emit, worker_processes=True
            )

        def done(result: object) -> None:
            self.progress.setText("Completed")
            self.enable_new_setup()
            self.completed.emit(result)

        self.launch(operation, done)
