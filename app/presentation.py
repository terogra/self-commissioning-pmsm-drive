"""Read-only tables and versioned evidence; never fit, gate, tune or simulate."""

from dataclasses import asdict
import hashlib
import json

from src.engineering_bundle import attempt_summary, json_value
from src.engineering_workflow import PARAMETER_NAMES, PARAMETER_UNITS, ROOT


def parameter_rows(result):
    estimates = {}
    for attempt in result.attempts:
        estimates.update(attempt_summary(attempt)["estimated_parameters"])
    return [{"Parameter": name, "Unit": unit, "Prior assumption": getattr(result.config.prior_assumptions, name),
        "Identified / known": (result.config.prior_assumptions.pole_pairs if name == "pole_pairs" else estimates.get(name)),
        "Controller value": getattr(result.controller_parameters, name)}
        for name, unit in zip(PARAMETER_NAMES, PARAMETER_UNITS)]


def overview_rows(result):
    """Display existing run state; no feasibility, quality or control calculation."""
    identified = ", ".join(row["Parameter"] for row in parameter_rows(result)
                           if row["Parameter"] != "pole_pairs" and row["Identified / known"] is not None)
    dynamic = result.dynamic_feasibility
    return (
        ("Commissioning", result.status),
        ("M17 simulation preset", result.config.scenario),
        ("Speed target [rpm]", f"{result.config.speed_target_rpm:g}"),
        ("DC bus [V]", f"{result.config.dc_bus_voltage_v:g}"),
        ("Identified parameters" if result.quality.accepted else "Estimates / prior retained", identified or "unavailable"),
        ("Steady-state feasibility", result.steady_feasibility.classification if result.steady_feasibility is not None else "unavailable"),
        ("Dynamic feasibility", "unavailable" if dynamic is None else
         "Predicted success" if dynamic.controller.predicted_closed_loop_success else "Predicted failure"),
        ("Firmware export", "Available" if result.firmware_available else "Blocked"),
    )


def attempt_rows(result):
    return [{"Stage": a.stage.value, "Attempt": a.number, "Quality": "ACCEPT" if a.quality.accepted else "REJECT",
        "Estimator succeeded": a.estimator_succeeded, "Reasons": "; ".join(a.quality.rejection_reasons),
        "Estimator failure": a.quality.estimator_failure, "Decision": a.retry_decision,
        "Adaptive action": a.retry_action, "Next configuration": None if a.next_config is None else json.dumps(json_value(a.next_config), sort_keys=True)}
        for a in result.attempts]


def estimate_rows(attempt):
    return [{"Parameter": name, "Unit": unit, "Estimate": getattr(attempt.estimate, name)}
            for name, unit in zip(PARAMETER_NAMES, PARAMETER_UNITS)
            if attempt.estimate is not None and hasattr(attempt.estimate, name)]


def controller_rows(result):
    current = asdict(result.controller_constants.current)
    speed = asdict(result.controller_constants.speed)
    units = {"Current": {"kp_d": "V/A", "kp_q": "V/A", "ki_d": "V/(A s)", "ki_q": "V/(A s)",
        "anti_windup_gain": "1/s", "dc_bus_voltage_v": "V", "voltage_limit_v": "V"},
        "Speed": {"kp": "A s/rad", "ki": "A/rad", "torque_constant_nm_per_a": "N m/A", "iq_limit_a": "A"}}
    return [{"Loop": loop, "Constant": name, "Unit": units[loop][name], "Value": value} for loop, values in (("Current", current), ("Speed", speed))
            for name, value in values.items()]


def metric_rows(result):
    if result.control is None: return []
    return [{"Metric": key, "Value": "unavailable" if value is None else str(value)} for key, value in result.control.metrics.items()]


def record_rows(record, omit=()):
    """Compact inspection table; field suffixes retain the backend's SI units."""
    values = json_value(record)
    return [{"Quantity": name, "Value": "unavailable" if value is None else
             (json.dumps(value) if isinstance(value, (list, dict)) else str(value))}
            for name, value in values.items() if name not in omit]


def load_committed_parity_evidence():
    path = ROOT/"results/firmware_parity/parity_summary.json"
    raw = path.read_bytes()
    summary = json.loads(raw)
    relative = max(({"group": group, "signal": signal, **metrics} for group, signals in summary["metrics"].items()
                    for signal, metrics in signals.items()), key=lambda row: row["max_relative_error"])
    flags = summary["saturation_flags"]
    return {"evidence_kind": "COMMITTED M18 VALIDATION EVIDENCE — not current-run parity",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(), "build": summary["build"],
        "compared_samples": summary["total_compared_samples"], "worst_absolute": summary["worst_absolute"],
        "worst_relative": relative, "saturation_agreement": {k: v for k, v in flags.items() if k != "boundary_probes"},
        "boundary_disagreements": sum(not p["agree"] for p in flags["boundary_probes"]),
        "boundary_note": "Strict > saturation flags can disagree at float32 rounding boundaries; all probes were retained."}
