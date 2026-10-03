"""Native Qt boundaries with real engineering results; no browser required."""

import ast
from dataclasses import replace
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.localization import set_language, t
from desktop.main import runtime_report
from desktop.main_window import MainWindow
from desktop.plots import PlotPanel
from desktop.runtime import resource_root
from desktop.services import WorkflowService
from desktop.tables import ResultTableModel
from src.engineering_bundle import run_summary
from src.engineering_reporting import commissioning_figure, control_figure
from src.engineering_workflow import EngineeringWorkflowConfig, ROOT, export_firmware_configuration, run_engineering_workflow


@pytest.fixture(scope="module")
def qt():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(scope="module")
def results():
    default = EngineeringWorkflowConfig()
    return tuple(run_engineering_workflow(c) for c in (default, replace(default, scenario="timing_one_sample")))


@pytest.fixture
def window(qt):
    widget = MainWindow()
    widget.show()
    qt.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qt.processEvents()
    set_language("tr")


def wait_until(qt, predicate, timeout=40):
    start = time.monotonic()
    while not predicate() and time.monotonic()-start < timeout:
        qt.processEvents()
        QTest.qWait(5)
    assert predicate(), "Qt operation did not finish"


def test_native_startup_defaults_and_runtime(window):
    assert window.windowTitle() == "PMSM Sürücü Devreye Alma Aracı"
    assert window.input_panel.language.currentData() == "tr"
    assert window.input_panel.configuration() == EngineeringWorkflowConfig()
    assert not window.busy and window.result is None
    assert window.run_button.text() == "Devreye Almayı Başlat"
    assert not window.firmware_button.isEnabled()
    assert runtime_report(window)["window_visible"]


def test_language_switch_preserves_inputs_results_and_exports(window, results, monkeypatch):
    window.present_result(results[0])
    before = json.dumps(run_summary(window.result), sort_keys=True)
    window.input_panel.controls["target"].setValue(900)
    scenario = window.input_panel.controls["scenario"]
    scenario.setCurrentIndex(scenario.findData("timing_one_sample"))
    monkeypatch.setattr(window.service, "run", lambda _: pytest.fail("Language switch recomputed commissioning"))
    for code, title in (("en", "PMSM Drive Commissioning Workbench"), ("tr", "PMSM Sürücü Devreye Alma Aracı")):
        window.input_panel.language.setCurrentIndex(window.input_panel.language.findData(code))
        assert window.windowTitle() == title
        assert window.input_panel.controls["target"].value() == 900
        assert scenario.currentData() == "timing_one_sample"
        assert window.result is results[0]
        assert window.firmware_button.isEnabled()
        assert json.dumps(run_summary(window.result), sort_keys=True) == before


def test_exact_corrected_turkish_terms(window):
    for source, target in {"Operating request": "Çalışma noktası", "Dynamic deadline [s]": "Dinamik süre sınırı [s]",
        "Available": "Kullanılabilir", "Blocked": "Engellendi", "M17 simulation preset": "M17 senaryosu",
        "Simulation errors": "İdeal olmayan etkiler"}.items(): assert t(source) == target


def test_real_native_worker_accepts_and_rejects_without_overlap(window, qt, results):
    received = []
    window.run_completed.connect(received.append)
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    assert window.busy and not window.run_button.isEnabled()
    first_thread = window._thread
    window.start_commissioning()
    assert window._thread is first_thread
    wait_until(qt, lambda: not window.busy)
    assert len(received) == 1 and window.result.quality.accepted
    assert window.firmware_button.isEnabled()
    assert len(window.result.attempts) == 3
    actual, direct = run_summary(window.result), run_summary(results[0])
    actual.pop("metadata"); direct.pop("metadata")
    assert actual == direct
    scenario = window.input_panel.controls["scenario"]
    scenario.setCurrentIndex(scenario.findData("timing_one_sample"))
    window.start_commissioning()
    wait_until(qt, lambda: not window.busy)
    assert len(received) == 2 and not window.result.quality.accepted
    assert not window.firmware_button.isEnabled()
    assert "standstill.excessive_residual" in window.reasons.text()
    assert window.result.controller_parameters == window.result.config.prior_assumptions
    actual, direct = run_summary(window.result), run_summary(results[1])
    actual.pop("metadata"); direct.pop("metadata")
    assert actual == direct
    assert window.input_panel.isEnabled() and window.run_button.isEnabled()


def test_adaptive_attempts_are_backend_records(window, qt):
    combo = window.input_panel.controls["mode"]
    combo.setCurrentIndex(combo.findData("adaptive"))
    window.start_commissioning()
    wait_until(qt, lambda: not window.busy)
    assert window.result.supervisor is not None
    assert window.result.attempts == window.result.supervisor.attempts
    assert window.result.quality.accepted


def test_worker_failure_restores_controls_and_logs(window, qt, monkeypatch, caplog):
    def fail(_): raise RuntimeError("test diagnostic")
    monkeypatch.setattr(window.service, "run", fail)
    dialogs = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: dialogs.append(args))
    window.start_commissioning()
    wait_until(qt, lambda: not window.busy)
    assert window.run_button.isEnabled() and window.input_panel.isEnabled()
    assert window.result is None and not window.firmware_button.isEnabled()
    assert dialogs and "Traceback" not in dialogs[0][2]
    assert "test diagnostic" in caplog.text


def test_busy_close_does_not_destroy_active_worker(window, qt, monkeypatch, results):
    import threading
    release = threading.Event()
    monkeypatch.setattr(window.service, "run", lambda _: (release.wait(10), results[0])[1])
    window.start_commissioning()
    window.close()
    assert window.isVisible() and window.busy
    release.set()
    wait_until(qt, lambda: not window.busy)
    window.close()
    assert not window.isVisible()


def test_native_save_dialog_exports_exact_existing_header(window, results, tmp_path, monkeypatch):
    window.present_result(results[0])
    destination = tmp_path/"config with spaces.h"
    dialogs = []
    def choose(*args):
        dialogs.append(args)
        return str(destination), "C header (*.h)"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    window.save_firmware()
    direct = export_firmware_configuration(results[0], tmp_path/"direct.h")
    assert dialogs and destination.read_bytes() == direct.read_bytes()
    window.present_result(results[1])
    window.save_firmware()
    assert len(dialogs) == 1 and not window.firmware_button.isEnabled()
    assert window.result.controller_parameters == window.result.config.prior_assumptions
    assert destination.read_bytes() == direct.read_bytes()


def test_native_bundle_save_uses_existing_export(window, results, tmp_path, monkeypatch):
    import zipfile
    window.present_result(results[1])
    path = tmp_path/"rejected.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), "ZIP (*.zip)"))
    window.save_bundle()
    with zipfile.ZipFile(path) as archive:
        assert "generated_motor_config.h" not in archive.namelist()
        assert json.loads(archive.read("run_summary.json"))["status"] == "REJECTED"


def test_table_retains_exact_values_and_codes(qt):
    value = .00119986651234567
    model = ResultTableModel([{"Value": value, "Reasons": "future_stage.exact_code"}])
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole) == value
    assert model.data(model.index(0, 1)) == "future_stage.exact_code"
    assert float(model.data(model.index(0, 0))) == pytest.approx(value, rel=1e-8)


def test_embedded_plots_keep_backend_numeric_artists(qt, results):
    result = results[0]
    for make in (lambda: control_figure(result), lambda: commissioning_figure(result.measurement_records[0], result.attempts[0].estimate)):
        panels = []
        for language in ("tr", "en"):
            set_language(language)
            figure = make()
            before = [line.get_ydata().copy() for ax in figure.axes for line in ax.lines]
            panel = PlotPanel(figure)
            panel.canvas.draw()
            after = [line.get_ydata() for ax in figure.axes for line in ax.lines]
            for a, b in zip(before, after): np.testing.assert_array_equal(a, b)
            panels.append((panel, after))
        for a, b in zip(panels[0][1], panels[1][1]): np.testing.assert_array_equal(a, b)
        for panel, _ in panels: panel.close(); panel.deleteLater()
    set_language("tr")


def test_resource_root_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resource_root() == ROOT
    assert (resource_root()/"results/firmware_parity/parity_summary.json").is_file()


def test_desktop_runtime_does_not_import_web_modules(tmp_path):
    code = '''
import importlib.abc, sys
class BlockWeb(importlib.abc.MetaPathFinder):
    def find_spec(self, name, *args):
        if name.startswith(('streamlit', 'uvicorn', 'flask', 'fastapi', 'PySide6.QtWebEngine')):
            raise AssertionError('Unexpected runtime dependency: '+name)
sys.meta_path.insert(0, BlockWeb())
from PySide6.QtWidgets import QApplication
from desktop.main_window import MainWindow
application = QApplication([])
window = MainWindow()
window.show()
application.processEvents()
assert window.isVisible()
window.close()
'''
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
    completed = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=environment,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr


def test_no_estimator_or_controller_implementations_in_qt():
    forbidden = {"src.identification", "src.rotating_identification", "src.mechanical_identification", "src.foc", "src.speed_control"}
    for path in (ROOT/"desktop").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ImportFrom) and node.module in forbidden for node in ast.walk(tree))
        assert not any(isinstance(node, ast.Import) and any(name.name.startswith(("streamlit", "webbrowser", "uvicorn"))
                       for name in node.names) for node in ast.walk(tree))
