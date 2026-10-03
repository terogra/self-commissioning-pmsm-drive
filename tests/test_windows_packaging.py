"""Native packaging gates; the historical engineering hash contract is retained."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from desktop.runtime import resource_root
from src.engineering_workflow import ROOT


def test_native_source_initializes_qt_from_an_unrelated_cwd(tmp_path):
    report = tmp_path/"source-qt.json"
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT), LOCALAPPDATA=str(tmp_path))
    completed = subprocess.run([sys.executable, "-m", "desktop", "--smoke-report", str(report)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    state = json.loads(report.read_text(encoding="utf-8"))
    assert state["qt_window_initialized"] and state["window_visible"]
    assert not state["frozen"] and state["forbidden_runtime_modules"] == []


def test_resource_lookup_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resource_root() == ROOT
    assert (resource_root()/"results/firmware_parity/parity_summary.json").is_file()


def test_failed_native_smoke_preserves_diagnostics_and_cleans_process(tmp_path):
    smoke = runpy.run_path(str(ROOT/"packaging/smoke_test.py"))["smoke_test"]
    with pytest.raises(RuntimeError): smoke(tmp_path/"does not exist.exe", tmp_path/"diagnostics", timeout=.2)
    report = json.loads((tmp_path/"diagnostics/smoke_result.json").read_text())
    assert not report["native_desktop_verified"] and report["failure"]
    assert "http_200" not in report


def test_archive_requires_native_exe_runtime_gate_and_has_integrity_hash(tmp_path):
    archive = runpy.run_path(str(ROOT/"packaging/archive.py"))["create_archive"]
    directory = tmp_path/"PMSM-Commissioning-Workbench"
    directory.mkdir()
    (directory/"PMSM-Commissioning-Workbench.exe").write_bytes(b"unit test fixture only")
    smoke = tmp_path/"smoke_result.json"
    smoke.write_text(json.dumps({"native_desktop_verified": False}))
    with pytest.raises(ValueError): archive(directory, tmp_path/"artifacts", "1.1.0", smoke)
    assert not (tmp_path/"artifacts").exists()
    smoke.write_text(json.dumps({"native_desktop_verified": True}))
    path, checksum = archive(directory, tmp_path/"artifacts", "1.1.0", smoke)
    assert path.name == "PMSM-Commissioning-Workbench-v1.1.0-Windows-x64.zip"
    assert checksum.read_text().split()[0] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_spec_is_windowed_qt_and_excludes_legacy_web_runtime():
    text = (ROOT/"packaging/windows.spec").read_text()
    assert "console=False" in text and "COLLECT(" in text
    assert "QtAgg" in text and "parity_summary.json" in text
    assert '"streamlit"' in text and "collect_all" not in text
    assert "PMSM-Commissioning-Workbench" in text
    launcher = (ROOT/"packaging/launcher.py").read_text()
    assert "from desktop.main import main" in launcher
    assert "bootstrap" not in launcher and "subprocess" not in launcher


def test_native_dependencies_are_separate_from_legacy():
    core = (ROOT/"requirements.txt").read_text().lower()
    windows = (ROOT/"packaging/requirements-windows.txt").read_text().lower()
    for requirements in (core, windows):
        assert "pyside6" in requirements
        assert not any(name in requirements for name in ("streamlit", "uvicorn", "fastapi", "flask", "pywebview"))
    assert "streamlit==" in (ROOT/"requirements-legacy.txt").read_text()


def test_windows_ci_uses_native_readiness_and_space_path_extraction():
    text = (ROOT/".github/workflows/windows-portable.yml").read_text()
    assert "QT_QPA_PLATFORM" in text and "offscreen" in text
    assert "PMSM extracted with spaces" in text
    assert "HTTP 200" not in text and "--port" not in text
    assert "tests/test_desktop.py" in text


def test_stable_engineering_sources_and_historical_evidence_are_unchanged():
    contract = json.loads((ROOT/"tests/v1_0_preservation.json").read_text())
    assert contract["baseline"] == "d3ae7f3ef62a814b5bc7a93ea737c73af1b819da"
    for name, metadata in contract["files"].items():
        raw = (ROOT/name).read_bytes()
        if not metadata["binary"]: raw = raw.replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == metadata["sha256"], name
