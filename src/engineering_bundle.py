"""Reproducible JSON/CSV/header/figure bundles for the real workflow."""

import csv
from dataclasses import fields, is_dataclass
from enum import Enum
import json
from math import isfinite
from pathlib import Path
from collections.abc import Mapping
import tempfile
import zipfile
import io

import numpy as np

from src.engineering_workflow import ROOT, export_firmware_configuration
from src.engineering_reporting import control_figure


def json_value(value):
    if isinstance(value, Enum): return value.value
    if is_dataclass(value): return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [json_value(v) for v in value]
    if isinstance(value, np.ndarray): return json_value(value.tolist())
    if isinstance(value, np.generic): return json_value(value.item())
    if isinstance(value, float) and not isfinite(value): return None
    if value is None or isinstance(value, (str, int, float, bool)): return value
    raise TypeError(f"Unsupported bundle value: {type(value).__name__}")


def attempt_summary(attempt):
    return {"stage": attempt.stage.value, "number": attempt.number,
        "configuration": json_value(attempt.config), "estimator_succeeded": attempt.estimator_succeeded,
        "quality": json_value(attempt.quality), "diagnostics": json_value(attempt.diagnostics),
        "estimated_parameters": {n: getattr(attempt.estimate, n) for n in ("Rs", "Ld", "Lq", "psi_f", "J", "B")
            if attempt.estimate is not None and hasattr(attempt.estimate, n)},
        "decision": attempt.retry_decision, "action": attempt.retry_action, "next_configuration": json_value(attempt.next_config)}


def run_summary(result):
    configuration = json_value(result.config)
    configuration.pop("simulation_truth")
    return {"bundle_schema": "pmsm-engineering-run-v1", "evidence_kind": "CURRENT RUN RESULTS",
        "metadata": json_value(result.metadata), "estimator_visible_configuration": configuration,
        "nonidealities": json_value(result.nonidealities), "status": result.status, "quality": json_value(result.quality),
        "controller_parameters": json_value(result.controller_parameters), "controller_constants": json_value(result.controller_constants),
        "steady_feasibility": json_value(result.steady_feasibility), "steady_classification": None if result.steady_feasibility is None else result.steady_feasibility.classification,
        "dynamic_feasibility": json_value(result.dynamic_feasibility),
        "control_metrics": None if result.control is None else json_value(result.control.metrics),
        "firmware_available": result.firmware_available, "firmware_configuration": json_value(result.firmware_config),
        "supervisor_state": None if result.supervisor is None else result.supervisor.state.value,
        "supervisor_terminal_reason": None if result.supervisor is None else result.supervisor.terminal_reason,
        "warnings": list(result.warnings), "simulation_evaluation_ground_truth": json_value(result.simulation_evaluation),
        "trace_export": {"uniform_stride": 25, "metrics_use_full_trace": True,
            "additional_rows": "final sample and both saturation-state transitions"},
        "nonfinite_diagnostic_serialization": "Nonfinite diagnostic values become JSON null, never a finite result."}


def _write_json(path, value):
    path.write_text(json.dumps(json_value(value), indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")


def export_run_bundle(result, directory):
    output = Path(directory).resolve()
    historical = (ROOT/"results").resolve()
    demo = historical/"v1_demo"
    if (output == historical or historical in output.parents) and output != demo and demo not in output.parents:
        raise ValueError("workflow.historical_results_are_protected")
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output/"run_summary.json", run_summary(result))
    _write_json(output/"commissioning_attempts.json", {
        "attempts": [attempt_summary(a) for a in result.attempts],
        "measurement_records": [{"stage": r.stage.value, "number": r.number,
            "configuration": json_value(r.config), "measurement_failure": r.measurement_failure,
            "sample_count": 0 if r.measurements is None else len(r.measurements.time_s),
            "noise_metadata": None if r.measurements is None else json_value(r.measurements.noise)} for r in result.measurement_records]})
    header, trace_path = output/"generated_motor_config.h", output/"control_trace.csv"
    if result.firmware_available:
        export_firmware_configuration(result, header)
    elif header.exists():
        header.unlink()  # exact managed filename; rejection must never leave a stale header
    if result.control is not None:
        trace = result.control.trace
        keys = [k for k, v in trace.items() if isinstance(v, np.ndarray) and v.ndim == 1]
        selected = set(range(0, len(trace["time"]), 25)) | {len(trace["time"])-1}
        for flag in ("voltage_saturated", "actual_bus_saturated"):
            selected.update(int(v) for v in np.flatnonzero(np.diff(trace[flag].astype(int)))+1)
        with trace_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["sample"]+keys)
            writer.writeheader()
            for k in sorted(selected): writer.writerow({"sample": k, **{n: json_value(trace[n][k]) for n in keys}})
    elif trace_path.exists():
        trace_path.unlink()
    figure = control_figure(result)
    figure.savefig(output/"summary_plot.png", dpi=140)
    figure.clear()
    return tuple(sorted(p for p in output.iterdir() if p.is_file()))


def run_bundle_zip(result):
    """Downloads contain a run's records; no historical result is substituted."""
    payload = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="pmsm-run-") as directory:
        paths = export_run_bundle(result, directory)
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in paths: archive.write(path, path.name)
    return payload.getvalue()
