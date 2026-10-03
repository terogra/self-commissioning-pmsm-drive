"""UI smoke/presentation and real demo reproduction; no interactive browser."""

import ast
import csv
from decimal import Decimal
import io
import json
import re
import zipfile

import numpy as np
import pytest

from app.__main__ import launch_command
from app.presentation import attempt_rows, controller_rows, load_committed_parity_evidence, parameter_rows
from experiments.v1_demo import DEMO_CONFIGURATIONS, generate_demo
from src.engineering_bundle import export_run_bundle, run_bundle_zip, run_summary
from src.engineering_workflow import EngineeringWorkflowConfig, ROOT, run_engineering_workflow
from src.version import __version__


@pytest.fixture(scope="module")
def demos():
    return tuple(run_engineering_workflow(c) for _, c in DEMO_CONFIGURATIONS)


def test_launch_is_one_command_and_bound_to_localhost():
    command = launch_command(["--server.headless=true"])
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4] == str(ROOT/"app/dashboard.py")
    assert "--server.address=127.0.0.1" in command
    assert command[-1] == "--server.headless=true"
    assert __version__ == "1.1.0"


def test_presentation_is_read_only_and_has_no_engineering_equations(demos):
    accepted, rejected = demos
    rows = parameter_rows(accepted)
    assert len(rows) == 7 and all(r["Unit"] for r in rows)
    assert len(controller_rows(accepted)) == 11
    assert all(row["Controller value"] == row["Prior assumption"] for row in parameter_rows(rejected))
    assert attempt_rows(rejected)[0]["Quality"] == "REJECT"
    tree = ast.parse((ROOT/"app/presentation.py").read_text(encoding="utf-8"))
    arithmetic = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)]
    assert all(isinstance(n.op, ast.Div) and isinstance(n.left, ast.Name) and n.left.id == "ROOT"
               and isinstance(n.right, ast.Constant) and isinstance(n.right.value, str) for n in arithmetic)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {"src.identification", "src.mechanical_identification", "src.foc", "src.speed_control", "src.controllers"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"run_engineering_workflow", "estimate_flux_linkage", "assess_commissioning"}


def test_committed_parity_is_labeled_and_not_current_run():
    evidence = load_committed_parity_evidence()
    assert "not current-run" in evidence["evidence_kind"]
    assert len(evidence["artifact_sha256"]) == 64
    assert evidence["compared_samples"] == 31484
    assert evidence["saturation_agreement"]["nonboundary_comparisons"] == evidence["saturation_agreement"]["nonboundary_agreements"]
    assert evidence["boundary_disagreements"] == 16  # committed Windows artifact, not a universal compiler result


def test_bundle_truth_is_explicit_and_rejected_data_remain_available(demos, tmp_path):
    accepted, rejected = demos
    for result in demos:
        summary = run_summary(result)
        assert "simulation_truth" not in summary["estimator_visible_configuration"]
        assert summary["simulation_evaluation_ground_truth"]["truth"]["J"] == result.config.simulation_truth.J
        assert summary["evidence_kind"] == "CURRENT RUN RESULTS"
    directory = tmp_path/"reused-output"
    export_run_bundle(accepted, directory)
    assert (directory/"generated_motor_config.h").exists()
    export_run_bundle(rejected, directory)
    assert not (directory/"generated_motor_config.h").exists()
    assert not (directory/"control_trace.csv").exists()
    attempts = json.loads((directory/"commissioning_attempts.json").read_text())
    assert attempts["attempts"][0]["quality"]["accepted"] is False
    assert attempts["attempts"][0]["estimated_parameters"]
    assert (directory/"summary_plot.png").stat().st_size > 10000


def test_bundle_protects_historical_results(demos):
    with pytest.raises(ValueError, match="historical_results"):
        export_run_bundle(demos[0], ROOT/"results/firmware_parity")


def test_download_bundle_is_a_current_run_zip(demos):
    payload = run_bundle_zip(demos[0])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {"run_summary.json", "commissioning_attempts.json", "generated_motor_config.h", "control_trace.csv", "summary_plot.png"}
        assert json.loads(archive.read("run_summary.json"))["estimator_visible_configuration"]["seed"] == 1901


def _compare_numbers(actual, expected):
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        for k in expected: _compare_numbers(actual[k], expected[k])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected): _compare_numbers(a, b)
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=1e-8, abs=1e-10)
    else: assert actual == expected


def test_one_command_demo_reproduces_committed_results_and_headers(tmp_path):
    # Real simulations are recomputed; historical artifacts are comparison-only.
    generate_demo(tmp_path)
    for name, _ in DEMO_CONFIGURATIONS:
        committed = ROOT/"results/v1_demo"/name
        generated = tmp_path/name
        a = json.loads((generated/"run_summary.json").read_text())
        b = json.loads((committed/"run_summary.json").read_text())
        # Timestamp/revision/dirty metadata does not influence computed results.
        a.pop("metadata"); b.pop("metadata")
        _compare_numbers(a, b)
        _compare_numbers(json.loads((generated/"commissioning_attempts.json").read_text()),
                         json.loads((committed/"commissioning_attempts.json").read_text()))
        if (committed/"generated_motor_config.h").exists():
            # v1.1 changes application/distribution version only. Preserve the historical
            # v1.0 demo artifact and ignore only the generated provenance version token.
            generated_header = (generated/"generated_motor_config.h").read_text(encoding="utf-8")
            committed_header = (committed/"generated_motor_config.h").read_text(encoding="utf-8")
            normalize_version = lambda value: re.sub(r"project \d+\.\d+\.\d+;", "project <version>;", value)
            assert normalize_version(generated_header) == normalize_version(committed_header)
            # Numeric trace equality across supported host platforms, not PNG-byte identity.
            def read_trace(path):
                with path.open(newline="", encoding="utf-8") as file:
                    return [{key: (value if value in ("True", "False") else float(value))
                             for key, value in row.items()} for row in csv.DictReader(file)]
            _compare_numbers(read_trace(generated/"control_trace.csv"), read_trace(committed/"control_trace.csv"))


def test_dashboard_headless_smoke_and_real_accept_reject_cycle():
    from streamlit.testing.v1 import AppTest
    from app import dashboard  # import must not launch a server or run commissioning
    assert callable(dashboard.main)
    app = AppTest.from_file(str(ROOT/"app/dashboard.py"), default_timeout=45).run()
    assert not app.exception
    assert app.selectbox(key="language_picker").value == "Türkçe"
    assert any("PMSM Otomatik Devreye Alma" in title.value for title in app.title)
    app.selectbox(key="language_picker").select("English").run()
    assert not app.exception
    assert any("Self-Commissioning PMSM Engineering" in title.value for title in app.title)
    app.selectbox(key="language_picker").select("Türkçe").run()
    assert not app.exception
    assert "result" not in app.session_state
    # AppTest bypasses native HTML step validation. Verify the actual widget
    # metadata separately so browser submission cannot silently be blocked.
    for widget in app.number_input:
        step = Decimal(str(widget.step))
        base = Decimal(str(widget.proto.min))
        offset = (Decimal(str(widget.value))-base)/step
        assert abs(offset-offset.to_integral_value()) < Decimal("1e-8"), widget.label
    assert app.number_input(key="hold").step == .001
    app.button(key="run_commissioning").click().run()
    assert not app.exception
    assert app.session_state["result"].quality.accepted
    app.button(key="generate_header").click().run()
    assert not app.exception
    assert "SIMULATED accepted full commissioning" in app.session_state["header"]
    app.selectbox(key="scenario_tr").select("timing_one_sample")
    app.button(key="run_commissioning").click().run()
    assert not app.exception
    assert not app.session_state["result"].quality.accepted
    assert "header" not in app.session_state
    assert not any(button.key == "generate_header" for button in app.button)
    assert any("standstill.excessive_residual" in e.value for e in app.error)
