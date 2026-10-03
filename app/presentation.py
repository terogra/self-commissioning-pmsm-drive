"""Read-only tables and versioned evidence; never fit, gate, tune or simulate."""

from dataclasses import asdict
import hashlib
import json

from app.i18n import text, value_text
from src.engineering_bundle import attempt_summary, json_value
from src.engineering_workflow import PARAMETER_NAMES, PARAMETER_UNITS, ROOT


def parameter_rows(result, language="en"):
    estimates = {}
    for attempt in result.attempts:
        estimates.update(attempt_summary(attempt)["estimated_parameters"])
    return [{
        text(language, "Parameter"): name,
        text(language, "Unit"): unit,
        text(language, "Prior assumption"): getattr(result.config.prior_assumptions, name),
        text(language, "Identified / known"): (
            result.config.prior_assumptions.pole_pairs if name == "pole_pairs" else estimates.get(name)
        ),
        text(language, "Controller value"): getattr(result.controller_parameters, name),
    } for name, unit in zip(PARAMETER_NAMES, PARAMETER_UNITS)]


def attempt_rows(result, language="en"):
    return [{
        text(language, "Stage"): value_text(language, a.stage.value),
        text(language, "Attempt"): a.number,
        text(language, "Quality"): value_text(language, "ACCEPT" if a.quality.accepted else "REJECT"),
        text(language, "Estimator succeeded"): a.estimator_succeeded,
        text(language, "Reasons"): "; ".join(a.quality.rejection_reasons),
        text(language, "Estimator failure"): a.quality.estimator_failure,
        text(language, "Decision"): a.retry_decision,
        text(language, "Adaptive action"): a.retry_action,
        text(language, "Next configuration"): (
            None if a.next_config is None else json.dumps(json_value(a.next_config), sort_keys=True)
        ),
    } for a in result.attempts]


def estimate_rows(attempt, language="en"):
    return [{
        text(language, "Parameter"): name,
        text(language, "Unit"): unit,
        text(language, "Estimate"): getattr(attempt.estimate, name),
    } for name, unit in zip(PARAMETER_NAMES, PARAMETER_UNITS)
      if attempt.estimate is not None and hasattr(attempt.estimate, name)]


def controller_rows(result, language="en"):
    current = asdict(result.controller_constants.current)
    speed = asdict(result.controller_constants.speed)
    units = {
        "Current": {
            "kp_d": "V/A", "kp_q": "V/A", "ki_d": "V/(A s)", "ki_q": "V/(A s)",
            "anti_windup_gain": "1/s", "dc_bus_voltage_v": "V", "voltage_limit_v": "V",
        },
        "Speed": {
            "kp": "A s/rad", "ki": "A/rad",
            "torque_constant_nm_per_a": "N m/A", "iq_limit_a": "A",
        },
    }
    return [{
        text(language, "Loop"): value_text(language, loop),
        text(language, "Constant"): name,
        text(language, "Unit"): units[loop][name],
        text(language, "Value"): value,
    } for loop, values in (("Current", current), ("Speed", speed))
      for name, value in values.items()]


def metric_rows(result, language="en"):
    if result.control is None:
        return []
    return [{
        text(language, "Metric"): key,
        text(language, "Value"): text(language, "unavailable") if value is None else str(value),
    } for key, value in result.control.metrics.items()]


def record_rows(record, omit=(), language="en"):
    """Compact inspection table; field suffixes retain the backend's SI units."""
    values = json_value(record)
    return [{
        text(language, "Quantity"): name,
        text(language, "Value"): text(language, "unavailable") if value is None else (
            json.dumps(value) if isinstance(value, (list, dict)) else str(value)
        ),
    } for name, value in values.items() if name not in omit]


def load_committed_parity_evidence():
    path = ROOT/"results/firmware_parity/parity_summary.json"
    raw = path.read_bytes()
    summary = json.loads(raw)
    relative = max(({"group": group, "signal": signal, **metrics} for group, signals in summary["metrics"].items()
                    for signal, metrics in signals.items()), key=lambda row: row["max_relative_error"])
    flags = summary["saturation_flags"]
    return {
        "evidence_kind": "COMMITTED M18 VALIDATION EVIDENCE — not current-run parity",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "build": summary["build"],
        "compared_samples": summary["total_compared_samples"],
        "worst_absolute": summary["worst_absolute"],
        "worst_relative": relative,
        "saturation_agreement": {k: v for k, v in flags.items() if k != "boundary_probes"},
        "boundary_disagreements": sum(not p["agree"] for p in flags["boundary_probes"]),
        "boundary_note": "Strict > saturation flags can disagree at float32 rounding boundaries; all probes were retained.",
    }
