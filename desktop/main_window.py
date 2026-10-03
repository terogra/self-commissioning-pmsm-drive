"""Native engineering workbench. All decisions and numbers come from the backend."""

import json
import logging

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QTabWidget, QToolBox, QVBoxLayout, QWidget,
)

from app.localization import DEFAULT_LANGUAGE, set_language, t
from app.presentation import (
    attempt_rows, controller_rows, estimate_rows, load_committed_parity_evidence,
    metric_rows, overview_rows, parameter_rows, record_rows,
)
from desktop.configuration import ConfigurationPanel
from desktop.plots import PlotPanel
from desktop.services import WorkflowService
from desktop.tables import result_table
from desktop.worker import CommissioningWorker
from src.engineering_bundle import json_value, run_summary
from src.engineering_reporting import commissioning_figure, control_figure
from src.version import RELEASE_STATUS, __version__


def label(message, *, code=False):
    widget = QLabel(message)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if code: widget.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    return widget


def inspector(value):
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    widget.setPlainText(json.dumps(json_value(value), indent=2, ensure_ascii=False))
    widget.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    widget.setMinimumHeight(160)
    return widget


def page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    layout = QVBoxLayout(body)
    scroll.setWidget(body)
    return scroll, layout


class MainWindow(QMainWindow):
    run_completed = Signal(object)
    run_failed = Signal(str)

    def __init__(self, service=None):
        super().__init__()
        self.service = service or WorkflowService()
        self.result = None
        self.busy = False
        self._thread = self._worker = None
        self.setMinimumSize(1000, 680)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1440, screen.width()-40), min(900, screen.height()-60))
        set_language(DEFAULT_LANGUAGE)
        self.input_panel = ConfigurationPanel()
        self.input_panel.language.currentIndexChanged.connect(self.change_language)
        self.run_button = QPushButton()
        self.run_button.setObjectName("run_commissioning")
        self.run_button.clicked.connect(self.start_commissioning)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.input_panel)
        left_layout.addWidget(self.progress)
        left_layout.addWidget(self.run_button)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.version_label = QLabel()
        self.summary = QGroupBox()
        self.summary_layout = QGridLayout(self.summary)
        self.reasons = label("", code=True)
        self.tabs = QTabWidget()
        self.firmware_button = QPushButton()
        self.firmware_button.setObjectName("export_firmware")
        self.firmware_button.clicked.connect(self.save_firmware)
        self.bundle_button = QPushButton()
        self.bundle_button.clicked.connect(self.save_bundle)
        self.actions = QHBoxLayout()
        self.actions.addStretch()
        self.actions.addWidget(self.bundle_button)
        self.actions.addWidget(self.firmware_button)
        right_layout.addWidget(self.version_label)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.reasons)
        right_layout.addWidget(self.tabs, 1)
        right_layout.addLayout(self.actions)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([370, 1070])
        self.setCentralWidget(splitter)
        self.retranslate()

    def change_language(self):
        set_language(self.input_panel.language.currentData())
        self.input_panel.retranslate()
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(t("Self-Commissioning PMSM Engineering"))
        self.version_label.setText(t("v{version} — {status}. Local simulation study; no hardware deployment.",
                                    version=__version__, status=t(RELEASE_STATUS)))
        self.run_button.setText(t("Run Commissioning"))
        self.firmware_button.setText(t("Export C header"))
        self.bundle_button.setText(t("Save run bundle"))
        self.summary.setTitle(t("Run summary"))
        self.render_result()
        self.statusBar().showMessage(t("Running…" if self.busy else "Ready"))

    def _clear_results_view(self):
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        current_tab = self.tabs.currentIndex()
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        self.reasons.clear()
        return current_tab

    def render_result(self):
        current_tab = self._clear_results_view()
        result = self.result
        self.firmware_button.setEnabled(result is not None and result.firmware_available and not self.busy)
        self.bundle_button.setEnabled(result is not None and not self.busy)
        if result is None:
            self.summary_layout.addWidget(label(t("Configure a simulation case and select Run Commissioning. Estimates and run metrics will be computed by the existing backend.")), 0, 0)
            scroll, layout = page()
            self.parity_view(layout)
            self.tabs.addTab(scroll, t("Firmware / M18"))
            return
        for i, (name, value) in enumerate(overview_rows(result)):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.addWidget(label(t(name)))
            display = label(t(value))
            font = display.font()
            font.setBold(True)
            display.setFont(font)
            cell_layout.addWidget(display)
            self.summary_layout.addWidget(cell, i//4, i%4)
        self.reasons.setText("; ".join(result.quality.rejection_reasons))
        self.reasons.setVisible(bool(result.quality.rejection_reasons))
        for message, build in (("Commissioning", self.commissioning_view), ("Parameters / controllers", self.parameters_view),
            ("Operating analysis", self.operating_view), ("Simulation evaluation", self.validation_view),
            ("Nonidealities", self.nonidealities_view), ("Firmware / M18", self.firmware_view)):
            scroll, layout = page()
            build(layout)
            self.tabs.addTab(scroll, t(message))
        if 0 <= current_tab < self.tabs.count(): self.tabs.setCurrentIndex(current_tab)

    def commissioning_view(self, layout):
        layout.addWidget(label(t("Sampled-data commissioning / attempt history")))
        rows = [{key: value for key, value in row.items() if key != "Next configuration"}
                for row in attempt_rows(self.result)]
        layout.addWidget(result_table(rows))
        if not rows: layout.addWidget(label(t("No estimator attempt completed. See the measurement/configuration failure below.")))
        toolbox = QToolBox()
        for attempt in self.result.attempts:
            scroll, details = page()
            details.addWidget(result_table(estimate_rows(attempt)))
            details.addWidget(label("; ".join(attempt.quality.rejection_reasons), code=True))
            if attempt.quality.estimator_failure: details.addWidget(label(attempt.quality.estimator_failure, code=True))
            details.addWidget(result_table([{"Check": c.name, "Measured value": c.value, "Limit": c.limit, "Passed": c.passed}
                                           for c in attempt.quality.checks]))
            details.addWidget(label(t("Residual units: V s for electrical/flux stages; N m s for mechanical. Local sensitivities are not confidence probabilities.")))
            details.addWidget(inspector({"diagnostics": attempt.diagnostics, "configuration": attempt.config,
                                         "next_retry_configuration": attempt.next_config}))
            record = next((r for r in self.result.measurement_records if r.stage == attempt.stage and r.number == attempt.number), None)
            if record is not None:
                if record.measurement_failure: details.addWidget(label(record.measurement_failure, code=True))
                details.addWidget(PlotPanel(commissioning_figure(record, attempt.estimate)))
            toolbox.addItem(scroll, f"{t(attempt.stage.value)} · {attempt.number} · {t('ACCEPT' if attempt.quality.accepted else 'REJECT')}")
        layout.addWidget(toolbox, 1)
        layout.addWidget(inspector({"metadata": self.result.metadata,
                                   "estimator_visible_configuration": run_summary(self.result)["estimator_visible_configuration"]}))

    def parameters_view(self, layout):
        layout.addWidget(label(t("Prior → identified → active controller")))
        layout.addWidget(result_table(parameter_rows(self.result)), 1)
        layout.addWidget(result_table(controller_rows(self.result)), 1)
        layout.addWidget(label(t("Motor values and gains come from existing retuning/controller constructors. Rejection retains all prior controller parameters.")))

    def operating_view(self, layout):
        layout.addWidget(label(t("Operating analysis — separate from commissioning quality")))
        if not self.result.quality.accepted:
            layout.addWidget(label(t("Unavailable: full commissioning rejected. No commissioned operation is fabricated.")))
            layout.addStretch()
            return
        steady, dynamic = self.result.steady_feasibility, self.result.dynamic_feasibility
        layout.addWidget(label(t("#### M14 steady operating feasibility").replace("#### ", "")))
        if steady is not None:
            layout.addWidget(label(t("Existing classification: ")+t(steady.classification)))
            layout.addWidget(result_table(record_rows(steady, omit=("assumptions",))))
        else: layout.addWidget(label(t("Steady analysis unavailable; see run warnings.")))
        layout.addWidget(label(t("#### M16 dynamic operating feasibility").replace("#### ", "")))
        layout.addWidget(label(t("Full dq transients can enter the band earlier. This quantity is not a universal physical lower bound.")))
        if dynamic is not None:
            layout.addWidget(label(t("**Quasi-steady model estimate**").replace("**", "")))
            layout.addWidget(result_table(record_rows(dynamic.quasi_steady, omit=("trajectory",))))
            layout.addWidget(label(t("**Controller-aware prediction on identified model**").replace("**", "")))
            layout.addWidget(result_table(record_rows(dynamic.controller, omit=("trace",))))
            layout.addWidget(inspector({"request": dynamic.request, "assumptions": dynamic.assumptions}))
        else: layout.addWidget(label(t("Dynamic analysis unavailable; see run warnings.")))
        layout.addWidget(label(t("M16 predicts a constant load from t=0. Validation below applies the separately configured load step. Nominal bus/ideal sensing are M16 assumptions; configured M17 errors affect the hidden-plant validation separately.")))

    def validation_view(self, layout):
        layout.addWidget(label(t("Closed-loop validation — Simulation evaluation / ground truth")))
        layout.addWidget(label(t("Evaluation-only information below is never used to accept commissioning or select retries.")))
        layout.addWidget(result_table(record_rows(self.result.simulation_evaluation.truth)))
        layout.addWidget(result_table([{"Parameter": name, "Post-hoc absolute error [%]": value}
                        for name, value in self.result.simulation_evaluation.parameter_absolute_error_percent.items()]))
        for warning in self.result.warnings: layout.addWidget(label(t(warning)))
        if self.result.control is None:
            layout.addWidget(label(t("No commissioned validation trace is available.")))
            return
        layout.addWidget(result_table(metric_rows(self.result)))
        layout.addWidget(label(t("Post-load metrics use existing M17/M15 definitions. iq tracking compares true currents to references mapped into the true frame. Recovery can be zero when the disturbance stays inside ±10 rpm; null means no finite recovery.")))
        layout.addWidget(PlotPanel(control_figure(self.result)))

    def nonidealities_view(self, layout):
        layout.addWidget(label(t("M17 simulation stress/error models")))
        layout.addWidget(inspector(self.result.nonidealities))
        layout.addWidget(label(t("Exposure controls commissioning, operation, or both; Rs drift applies only during operation. Nominal-bus FOC command and true terminal voltage are distinct; extra actual-bus clipping is not fed back into nominal anti-windup.")))
        if self.result.control is not None:
            layout.addWidget(label(t("#### Simulation evaluation / ground truth").replace("#### ", "")))
            trace = self.result.control.trace
            layout.addWidget(result_table(record_rows({"nominal_bus_voltage_v": trace["dc_bus_voltage"],
                "actual_bus_voltage_v": trace["actual_dc_bus_voltage"],
                "terminal_command_discrepancy_rmse_v": self.result.control.metrics.get("terminal_command_discrepancy_rmse_v")})))
        layout.addWidget(label(t("Measured/true current and commanded/terminal voltage curves are in the Simulation evaluation tab.")))
        layout.addStretch()

    def firmware_view(self, layout):
        layout.addWidget(label(t("Portable firmware-ready control configuration — not deployed MCU firmware. No target timing, hardware validation or MISRA compliance is claimed.")))
        if self.result.firmware_available: layout.addWidget(inspector(self.result.firmware_config))
        else: layout.addWidget(label(t("Firmware export unavailable: full commissioning was rejected or the export configuration failed. Prior assumptions cannot be exported as commissioned estimates.")))
        self.parity_view(layout)

    def parity_view(self, layout):
        layout.addWidget(label(t("#### COMMITTED M18 VALIDATION EVIDENCE").replace("#### ", "")))
        layout.addWidget(label(t("Versioned evidence for the portable core; not a new parity test of this run. No compiler or replay executes on UI interaction.")))
        try:
            evidence = load_committed_parity_evidence()
            layout.addWidget(inspector(evidence))
            layout.addWidget(label(t(evidence["boundary_note"])))
        except (OSError, ValueError, KeyError):
            logging.exception("Committed parity evidence unavailable")
            layout.addWidget(label(t("Committed parity evidence unavailable: {error}", error=t("See diagnostic log"))))

    def set_busy(self, value):
        self.busy = value
        self.input_panel.setEnabled(not value)
        self.run_button.setEnabled(not value)
        self.progress.setVisible(value)
        self.firmware_button.setEnabled(not value and self.result is not None and self.result.firmware_available)
        self.bundle_button.setEnabled(not value and self.result is not None)
        self.statusBar().showMessage(t("Running…" if value else "Ready"))

    def start_commissioning(self):
        if self.busy: return
        try: configuration = self.input_panel.configuration()
        except Exception as exc:
            logging.exception("Invalid UI configuration")
            self.show_error(str(exc))
            return
        self.result = None
        self.set_busy(True)
        self.render_result()
        self._thread = QThread(self)
        self._worker = CommissioningWorker(self.service, configuration)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self.present_result)
        self._worker.failed.connect(self.worker_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self.thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def present_result(self, result):
        self.result = result
        self.render_result()
        self.run_completed.emit(result)

    def worker_failed(self, error):
        self.run_failed.emit(error)
        self.show_error(error)

    def thread_finished(self):
        self._thread = self._worker = None
        self.set_busy(False)

    def show_error(self, detail):
        QMessageBox.critical(self, t("Run failed"), t("Operation failed. See the diagnostic log for details.")+"\n"+detail)

    def save_firmware(self):
        if self.result is None or not self.result.firmware_available: return
        path, _ = QFileDialog.getSaveFileName(self, t("Export C header"), "generated_motor_config.h", "C header (*.h)")
        if path:
            try:
                self.service.export_firmware(self.result, path)
                self.statusBar().showMessage(t("Saved: {path}", path=path))
            except Exception as exc:
                logging.exception("Firmware export failed")
                self.show_error(type(exc).__name__)

    def save_bundle(self):
        if self.result is None: return
        path, _ = QFileDialog.getSaveFileName(self, t("Save run bundle"),
            f"pmsm_{self.result.config.scenario}_{self.result.config.seed}.zip", "ZIP (*.zip)")
        if path:
            try:
                self.service.export_bundle(self.result, path)
                self.statusBar().showMessage(t("Saved: {path}", path=path))
            except Exception as exc:
                logging.exception("Run bundle export failed")
                self.show_error(type(exc).__name__)

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
            self.statusBar().showMessage(t("Wait for commissioning to finish before closing."))
        else: event.accept()
