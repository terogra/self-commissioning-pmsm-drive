"""M16: prediction first; independent hidden-plant validation second.

Run development, freeze the method/protocol, then run evaluation. Every drawn
motor/request has a row, including unavailable commissioning and model errors.
"""

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np

from experiments.operating_feasibility import commission_plant, write_csv
from src.dynamic_feasibility import (
    DynamicAnalysisConfig, DynamicOperatingRequest, _commissioned_model,
    assess_dynamic_operating_point, assess_quasi_steady_capability, evaluate_controller_trace,
)
from src.mechanical_excitation import MechanicalExcitationConfig
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.speed_foc_simulation import run_speed_foc_simulation


OUTPUT = Path("results/dynamic_operating_feasibility")
SEEDS = {"development": 20261002, "evaluation": 20261003}
CONFIG = DynamicAnalysisConfig()
SCENARIOS = ("fast_easy", "deadline_limited", "longer_deadline", "current_limited",
             "voltage_high_speed", "tolerance_boundary", "unreachable", "moving_start")
SEMANTICS_CORRECTION = (
    "Naming corrected after the original held-out finding: full dq transients can enter "
    "before the quasi-steady estimate even on the same commissioned model. Original "
    "evaluation evidence, numerical method, seeds and scoring are unchanged."
)


def requests(full, rng=None):
    """Request design uses only identified values; no observed outcomes."""
    slow = assess_operating_point(full, OperatingPointRequest(1000, .005, 48, 5))
    high = assess_operating_point(full, OperatingPointRequest(2000, .05, 48, 5))
    boundary = assess_operating_point(full, OperatingPointRequest(1000, .05, 48, 5))
    # Drawn current multiplier broadens finite-time difficulty, never truth-based.
    multiplier = 1.10 if rng is None else float(rng.uniform(1.03, 1.30))
    moving_speed = 250 if rng is None else float(rng.uniform(150, 400))
    slow_limit = multiplier*slow.required_iq_a
    return dict(zip(SCENARIOS, (
        DynamicOperatingRequest(0, 250, .02, 24, 3, .6),
        DynamicOperatingRequest(0, 1000, .005, 48, slow_limit, .6),
        DynamicOperatingRequest(0, 1000, .005, 48, slow_limit, 4),
        DynamicOperatingRequest(0, 1000, .005, 48, max(.8, 2*slow_limit), .6),
        DynamicOperatingRequest(0, 2000, .05, high.required_voltage_magnitude_v*np.sqrt(3)*1.01, 5, .6),
        DynamicOperatingRequest(0, 1000, .05, boundary.required_voltage_magnitude_v*np.sqrt(3)*.995, 5, .6),
        DynamicOperatingRequest(0, 2000, .05, 12, 5, .6),
        DynamicOperatingRequest(moving_speed, 1000, .02, 24, 2, .6),
    )))


def compare_case(plant, full, request, **metadata):
    prediction = assess_dynamic_operating_point(full, request, CONFIG)
    # The only truth-based control simulation begins after prediction is complete.
    simulation = run_speed_foc_simulation(plant_params=plant,
        controller_params=_commissioned_model(full), dt=CONFIG.simulation_dt_s,
        simulation_time=request.deadline_s, initial_speed_rpm=request.initial_speed_rpm,
        speed_ref_rpm=request.target_speed_rpm, load_step_time=0,
        load_step_torque=request.load_torque_nm, dc_bus_voltage=request.dc_bus_voltage_v,
        current_limit_a=request.current_limit_a)
    actual = evaluate_controller_trace(simulation, request, CONFIG.simulation_dt_s, CONFIG.trace_interval_s)
    p, c = prediction.quasi_steady, prediction.controller
    factors = ";".join(name for name, flag in (("current", p.current_limited_on_path),
        ("voltage", p.voltage_limited_on_path), ("coincident", p.coincident_limits_on_path)) if flag)
    row = {**metadata, "status": "evaluated", **asdict(request),
        "exact_target_steady_feasible": prediction.exact_target_steady_state.feasible,
        "tolerance_band_steady_feasible": prediction.tolerance_band_steady_state.feasible,
        **{k: v for k, v in asdict(p).items() if k not in ("trajectory", "reasons")},
        "limiting_factors": factors, "prediction_success": c.predicted_closed_loop_success,
        "actual_success": actual.predicted_closed_loop_success,
        "prediction_first_entry_s": c.first_band_entry_time_s,
        "actual_first_entry_s": actual.first_band_entry_time_s,
        "prediction_qualified_entry_s": c.qualified_band_entry_time_s,
        "actual_qualified_entry_s": actual.qualified_band_entry_time_s,
        "prediction_hold_completion_s": c.hold_completion_time_s,
        "actual_hold_completion_s": actual.hold_completion_time_s,
        "qualified_entry_error_s": (None if c.qualified_band_entry_time_s is None or actual.qualified_band_entry_time_s is None
                                    else c.qualified_band_entry_time_s-actual.qualified_band_entry_time_s),
        "prediction_in_band_at_deadline": c.in_band_at_deadline,
        "actual_in_band_at_deadline": actual.in_band_at_deadline,
        "prediction_saturation_fraction": c.saturation_fraction,
        "actual_saturation_fraction": actual.saturation_fraction,
        "prediction_max_voltage_utilization": c.maximum_voltage_utilization,
        "actual_max_voltage_utilization": actual.maximum_voltage_utilization,
        "prediction_max_measured_current_a": c.maximum_measured_current_a,
        "actual_max_measured_current_a": actual.maximum_measured_current_a,
        "prediction_minimum_speed_rpm": c.minimum_speed_rpm,
        "actual_minimum_speed_rpm": actual.minimum_speed_rpm,
        "actual_final_speed_rpm": actual.trace[-1].speed_rpm,
        "reasons": ";".join(prediction.reasons), "actual_reasons": ";".join(actual.reasons)}
    return row, prediction, actual


def summary(rows):
    valid = [r for r in rows if r["status"] == "evaluated"]
    errors = [r["qualified_entry_error_s"] for r in valid if r["qualified_entry_error_s"] is not None]
    return {"total_cases": len(rows), "evaluated_cases": len(valid),
        "unavailable_or_error_cases": len(rows)-len(valid),
        "prediction_agreement": sum(r["prediction_success"] == r["actual_success"] for r in valid),
        "predicted_successes": sum(r["prediction_success"] for r in valid),
        "actual_successes": sum(r["actual_success"] for r in valid),
        "false_predicted_success": sum(r["prediction_success"] and not r["actual_success"] for r in valid),
        "false_predicted_failure": sum(not r["prediction_success"] and r["actual_success"] for r in valid),
        "quasi_steady_deadline_met": sum(r["quasi_steady_deadline_met"] is True for r in valid),
        "quasi_steady_deadline_missed_but_actual_success": sum(r["quasi_steady_deadline_met"] is False and r["actual_success"] for r in valid),
        "actual_entry_before_quasi_steady_estimate": sum(r["actual_first_entry_s"] is not None
            and r["quasi_steady_transition_time_estimate_s"] is not None
            and r["actual_first_entry_s"] < r["quasi_steady_transition_time_estimate_s"] for r in valid),
        "both_qualified_count": len(errors),
        "qualified_entry_error_median_s": float(np.median(errors)) if errors else None,
        "qualified_entry_absolute_error_max_s": float(np.max(np.abs(errors))) if errors else None,
        "limiting_factor_distribution": dict(Counter(r["limiting_factors"] for r in valid)),
        "brief_negative_actual_speed_cases": sum(r["actual_minimum_speed_rpm"] < 0 for r in valid)}


def run_population(population):
    rng = np.random.default_rng(SEEDS[population])
    rows, audits = [], []
    for motor_id in range(3 if population == "development" else 5):
        plant = PMSMParameters(Rs=float(rng.uniform(.35, .65)), Ld=float(rng.uniform(.8e-3, 1.4e-3)),
            Lq=float(rng.uniform(.7e-3, 1.3e-3)), psi_f=float(rng.uniform(.015, .028)),
            J=float(rng.uniform(3e-4, 8e-4)), B=float(rng.uniform(.8e-4, 2.5e-4)))
        seed = int(rng.integers(0, 2**31-3))
        try:
            full = commission_plant(plant, seed, MechanicalExcitationConfig(seed=seed+2))
            accepted = full.quality.accepted
            reason = ";".join(full.quality.rejection_reasons)
        except (ValueError, FloatingPointError, OverflowError) as exc:
            full, accepted, reason = None, False, str(exc)
        audits.append({"motor_id": motor_id, "measurement_seed": seed, "true_evaluation_only": asdict(plant),
            "commissioning_accepted": accepted, "reasons": reason,
            "identified": asdict(_commissioned_model(full)) if accepted else None})
        if not accepted:
            rows.extend(dict(motor_id=motor_id, scenario=name, status="commissioning_unavailable", reasons=reason)
                        for name in SCENARIOS)
            continue
        for name, request in requests(full, rng).items():
            try:
                row, _, _ = compare_case(plant, full, request, motor_id=motor_id, scenario=name)
            except (ValueError, FloatingPointError, OverflowError) as exc:
                row = dict(motor_id=motor_id, scenario=name, status="evaluation_error", reasons=str(exc))
            rows.append(row)
    return rows, audits


def representative():
    plant = PMSMParameters(Rs=.56, Ld=.0014, Lq=.0008, psi_f=.015, J=.0005, B=.0003)
    full = commission_plant(plant)
    if not full.quality.accepted:
        raise ValueError("Representative commissioning unavailable")
    rows, traces = [], {}
    for name, request in requests(full).items():
        row, pred, actual = compare_case(plant, full, request, scenario=name)
        rows.append(row)
        traces[name] = (pred, actual)
    write_csv(OUTPUT/"representative.csv", rows)
    save_json(OUTPUT/"representative_model.json", {"true_evaluation_only": asdict(plant),
        "identified": asdict(_commissioned_model(full)), "assumptions": pred.assumptions})
    write_csv(OUTPUT/"representative_traces.csv", [dict(scenario=name, model=model, **asdict(s))
        for name, (pred, actual) in traces.items() for model, record in (("prediction", pred.controller), ("hidden_plant", actual))
        for s in record.trace])
    plot_representative(traces)
    plot_capability_map(full)
    return rows


def retrospective():
    """Replay M14 plants/estimates, retain the original outcomes separately.

    M16 intentionally applies constant load from t=0 rather than M14's step at
    0.3 s, and a sampled hold criterion rather than a terminal-window current
    criterion. These are a sanity check, not an exact rescore of old records.
    """
    audits = json.loads(Path("results/operating_feasibility/held_out_plants.json").read_text(encoding="utf-8"))
    with Path("results/operating_feasibility/held_out.csv").open(newline="", encoding="utf-8") as handle:
        old_rows = {int(r["motor_id"]): r for r in csv.DictReader(handle) if r["scenario"] == "acceleration_limited"}
    rows = []
    for audit in audits:
        plant = PMSMParameters(**audit["true"])
        full = commission_plant(plant, audit["seed"], MechanicalExcitationConfig(seed=audit["seed"]+2))
        old = old_rows[audit["motor_id"]]
        if not full.quality.accepted:
            rows.append(dict(motor_id=audit["motor_id"], status="commissioning_unavailable"))
            continue
        for deadline in (.6, 4):
            request = DynamicOperatingRequest(0, 1000, .005, 48, float(old["current_limit_a"]), deadline)
            row, _, _ = compare_case(plant, full, request, motor_id=audit["motor_id"], scenario="m14_acceleration_limited",
                historical_0_6_success=old["closed_loop_dynamic_success"], historical_4_success=old["extended_run_success"])
            rows.append(row)
    write_csv(OUTPUT/"m14_retrospective.csv", rows)
    return rows


def plot_representative(traces):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    selected = ("fast_easy", "deadline_limited", "longer_deadline", "current_limited", "tolerance_boundary", "unreachable")
    for ax, name in zip(axes.flat, selected):
        pred, actual = traces[name]
        req = pred.request
        ax.axhspan(req.target_speed_rpm-req.speed_tolerance_rpm, req.target_speed_rpm+req.speed_tolerance_rpm,
                   color="grey", alpha=.2, label="Acceptance band")
        for label, record, style in (("Commissioned prediction", pred.controller, "-"), ("Hidden-plant validation", actual, "--")):
            ax.plot([s.time_s for s in record.trace], [s.speed_rpm for s in record.trace], style, label=label)
        if pred.quasi_steady.quasi_steady_transition_time_estimate_s is not None:
            t = pred.quasi_steady.quasi_steady_transition_time_estimate_s
            if t <= req.deadline_s:
                ax.axvline(t, color="green", linestyle=":", label="Quasi-steady entry estimate")
        ax.set(title=name.replace("_", " "), xlabel="Time [s]", ylabel="Speed [rpm]")
        ax.grid(alpha=.25)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("M16: sampled hold before deadline; constant load from t=0")
    fig.tight_layout()
    fig.savefig(OUTPUT/"representative_dynamics.png", dpi=160)
    plt.close(fig)


def plot_capability_map(full):
    currents, speeds = np.linspace(.4, 3, 27), np.linspace(250, 2500, 31)
    rows = []
    for speed in speeds:
        for current in currents:
            req = DynamicOperatingRequest(0, float(speed), .005, 24, float(current), 4)
            p = assess_quasi_steady_capability(full, req)
            rows.append(dict(target_speed_rpm=speed, current_limit_a=current,
                quasi_steady_transition_time_estimate_s=p.quasi_steady_transition_time_estimate_s,
                quasi_steady_band_reachable=p.quasi_steady_band_reachable, integration_converged=p.integration_converged))
    write_csv(OUTPUT/"transition_time_map.csv", rows)
    plot_capability_map_rows(rows)


def plot_capability_map_rows(rows):
    """Render saved grid values; relabeling does not run identification/control."""
    import matplotlib.pyplot as plt
    currents = sorted({r["current_limit_a"] for r in rows})
    speeds = sorted({r["target_speed_rpm"] for r in rows})
    grid = {(r["target_speed_rpm"], r["current_limit_a"]): r for r in rows}
    values = [[(grid[s, i]["quasi_steady_transition_time_estimate_s"]
                if grid[s, i]["quasi_steady_band_reachable"] else np.nan)
               for i in currents] for s in speeds]
    fig, ax = plt.subplots(figsize=(9, 5))
    mesh = ax.pcolormesh(currents, speeds, np.ma.masked_invalid(values), shading="nearest", cmap="viridis", vmin=0, vmax=4)
    ax.set_facecolor("#dddddd")
    fig.colorbar(mesh, ax=ax, label="Quasi-steady band-entry estimate [s]; color clipped at 4 s")
    ax.set(xlabel="Current reference design limit [A]", ylabel="Requested speed [rpm]",
           title="Quasi-steady id=0 model: 24 V, 0.005 N m; grey = model-unreachable")
    fig.tight_layout()
    fig.savefig(OUTPUT/"transition_time_map.png", dpi=160)
    plt.close(fig)


def plot_saved_artifacts():
    """Update labels using original CSV evidence, without rerunning a population."""
    def read_rows(name):
        with (OUTPUT/name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    saved = read_rows("representative_traces.csv")
    traces = {}
    for row in read_rows("representative.csv"):
        name = row["scenario"]
        req = DynamicOperatingRequest(**{k: float(row[k]) for k in DynamicOperatingRequest.__dataclass_fields__})
        def record(model):
            return SimpleNamespace(trace=tuple(SimpleNamespace(
                **{k: float(r[k]) for k in ("time_s", "speed_rpm", "iq_reference_a", "voltage_utilization")})
                for r in saved if r["scenario"] == name and r["model"] == model))
        estimate = row["quasi_steady_transition_time_estimate_s"]
        pred = SimpleNamespace(request=req, controller=record("prediction"),
            quasi_steady=SimpleNamespace(quasi_steady_transition_time_estimate_s=float(estimate) if estimate else None))
        traces[name] = (pred, record("hidden_plant"))
    plot_representative(traces)
    rows = read_rows("transition_time_map.csv")
    for row in rows:
        for k in ("target_speed_rpm", "current_limit_a", "quasi_steady_transition_time_estimate_s"):
            row[k] = float(row[k]) if row[k] else None
        row["quasi_steady_band_reachable"] = row["quasi_steady_band_reachable"] == "True"
    plot_capability_map_rows(rows)


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--population", choices=SEEDS)
    mode.add_argument("--replot-saved", action="store_true", help="Relabel original evidence without rerunning simulations")
    args = parser.parse_args()
    matplotlib.use("Agg")
    if args.replot_saved:
        plot_saved_artifacts()
        print("Replotted original saved evidence; no population or simulation rerun.")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, audit = run_population(args.population)
    name = "development" if args.population == "development" else "held_out"
    write_csv(OUTPUT/f"{name}.csv", rows)
    save_json(OUTPUT/f"{name}_plants.json", audit)
    result = summary(rows)
    save_json(OUTPUT/f"{name}_summary.json", {"seed": SEEDS[args.population], "plants": len(audit), **result})
    if args.population == "evaluation":
        reps, retro = representative(), retrospective()
        save_json(OUTPUT/"summary.json", {"analysis_config": asdict(CONFIG), "seeds": SEEDS,
            "semantics_correction": SEMANTICS_CORRECTION,
            "development": json.loads((OUTPUT/"development_summary.json").read_text(encoding="utf-8")),
            "representative": summary(reps), "held_out": {"plants": len(audit), **result}, "m14_retrospective": summary(retro),
            "criterion": "Contiguous sampled hold in max(1 rpm, 1% target) for 0.1 s completed before deadline; finite signals and |iq_ref|<=Imax",
            "protocol": "Method fixed after development and before independent seed evaluation; no outcome-based gate or algorithm tuning",
            "limits": "Small correlated scenario sample; point estimates; quasi-steady time estimate is not a physical minimum or universal lower bound; no hardware guarantee"})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
