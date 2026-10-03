"""Portable-launcher contracts. Actual frozen HTTP runtime is a separate CI gate."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

import pytest

from app.portable import configure_streamlit, launch_settings
from app.runtime import dashboard_path
from src.engineering_workflow import ROOT


def test_portable_launcher_forces_loopback_and_headless_settings():
    normal = launch_settings({})
    assert normal["server.address"] == "127.0.0.1"
    assert normal["server.headless"] is False
    assert normal["server.fileWatcherType"] == "none"
    assert launch_settings({"PMSM_HEADLESS": "1", "PMSM_PORT": "18551"})["server.port"] == 18551
    for invalid in ({"PMSM_HEADLESS": "maybe"}, {"PMSM_PORT": "0"}, {"PMSM_PORT": "65536"}):
        with pytest.raises(ValueError): launch_settings(invalid)


def test_resource_lookup_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert dashboard_path() == ROOT/"app/dashboard.py"
    assert dashboard_path().is_file()


def test_effective_streamlit_config_overrides_ambient_network_settings(monkeypatch):
    from streamlit import config
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    settings = launch_settings({"PMSM_HEADLESS": "1", "PMSM_PORT": "18561"})
    try:
        configure_streamlit(settings)
        assert config.get_option("server.address") == "127.0.0.1"
        assert config.get_option("server.port") == 18561
        assert config.get_option("server.headless") is True
        assert config.get_option("global.developmentMode") is False
    finally:
        monkeypatch.delenv("STREAMLIT_SERVER_ADDRESS")
        config.get_config_options(force_reparse=True)


def test_source_command_actually_serves_http_headlessly(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = dict(os.environ, PMSM_HEADLESS="1")
    log = tmp_path/"source-server.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen([sys.executable, "-m", "app", "--server.headless=true", f"--server.port={port}"],
            cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
        try:
            start = time.monotonic()
            while time.monotonic()-start < 20:
                assert process.poll() is None, log.read_text(encoding="utf-8", errors="replace")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                        assert response.status == 200
                    break
                except (URLError, OSError): time.sleep(.2)
            else: pytest.fail(log.read_text(encoding="utf-8", errors="replace"))
        finally:
            # Source path intentionally has a Streamlit child; stop both on Windows.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                import signal
                os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=10)


def test_failed_smoke_always_prints_exit_code_stdout_and_stderr(tmp_path, monkeypatch, capsys):
    module = runpy.run_path(str(ROOT/"packaging/smoke_test.py"))
    class FailedProcess:
        returncode = 23
        def poll(self): return self.returncode
    def failed_popen(*args, **kwargs):
        kwargs["stdout"].write("startup stdout evidence\n")
        kwargs["stderr"].write("startup stderr evidence\n")
        return FailedProcess()
    monkeypatch.setattr(subprocess, "Popen", failed_popen)
    # Avoid spawning netstat via the mocked Popen; port dump is optional here.
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: type("Ports", (), {"stdout": "port diagnostics"})())
    with pytest.raises(RuntimeError, match="exited before readiness"):
        module["smoke_test"](tmp_path/"failed.exe", tmp_path/"diagnostics", port=18554)
    text = capsys.readouterr().out
    assert "Process exit code: 23" in text
    assert "startup stdout evidence" in text and "startup stderr evidence" in text


def test_archive_requires_success_and_checksum_matches(tmp_path):
    archive = runpy.run_path(str(ROOT/"packaging/archive.py"))["create_archive"]
    directory = tmp_path/"portable folder with spaces"
    directory.mkdir()
    (directory/"PMSM Engineering App.exe").write_bytes(b"unit test fixture only")
    smoke = tmp_path/"smoke_result.json"
    smoke.write_text(json.dumps({"http_200": False}))
    with pytest.raises(ValueError): archive(directory, tmp_path/"artifacts", "1.1.0", smoke)
    assert not (tmp_path/"artifacts").exists()
    smoke.write_text(json.dumps({"http_200": True}))
    path, checksum = archive(directory, tmp_path/"artifacts", "1.1.0", smoke)
    assert path.name == "PMSM-Engineering-App-v1.1.0-Windows-x64.zip"
    assert checksum.read_text().split()[0] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_spec_bundles_static_assets_dynamic_modules_and_evidence():
    text = (ROOT/"packaging/windows.spec").read_text()
    assert 'collect_all("streamlit")' in text
    assert 'collect_submodules("src")' in text
    assert "parity_summary.json" in text
    assert "console=True" in text and "COLLECT(" in text
    launcher = (ROOT/"app/portable.py").read_text()
    assert "bootstrap.run(" in launcher
    assert "subprocess.call" not in launcher


def test_stable_engineering_sources_and_historical_evidence_are_unchanged():
    contract = json.loads((ROOT/"tests/v1_0_preservation.json").read_text())
    assert contract["baseline"] == "d3ae7f3ef62a814b5bc7a93ea737c73af1b819da"
    for name, metadata in contract["files"].items():
        data = (ROOT/name).read_bytes()
        if not metadata["binary"]:
            data = data.replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == metadata["sha256"], name
