"""M17 characterization with frozen algorithms/gates and evaluation-only truth."""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

import matplotlib
import numpy as np

from experiments.adaptive_commissioning import (_error_fields, _estimates_adaptive,
    _estimates_one_shot, NAMES, PRIOR)
from experiments.commissioning_recovery import _performance_metrics
from experiments.operating_feasibility import write_csv
from src.adaptive_commissioning import run_adaptive_commissioning, Stage, RetryPolicy, _standstill_quality
from src.commissioning import commission_from_measurements
from src.commissioning_quality import QualityPolicy
from src.drive_nonidealities import (DriveNonidealities, CurrentMeasurementErrors, VoltageMeasurementErrors,
    FrameErrors, TimingErrors, ActuationErrors, OperatingDrift)
from src.dynamic_feasibility import DynamicOperatingRequest, assess_dynamic_operating_point, evaluate_controller_trace
from src.full_commissioning import complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.mechanical_identification import MechanicalQualityPolicy
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation


OUTPUT = Path("results/nonideality_robustness")
SEEDS = {"development": 20261004, "evaluation": 20261005}
MOTOR_COUNTS = {"development": 2, "evaluation": 3}
EXPOSURES = ("commissioning_only", "operation_only", "combined")
IDEAL = DriveNonidealities()


@dataclass(frozen=True)
class Scenario:
    name: str
    family: str
    severity: str
    errors: DriveNonidealities


def scenarios():
    """Illustrative stress levels, not device specs; fixed across every motor."""
    mild = DriveNonidealities(current=CurrentMeasurementErrors((1.01, .99, 1.), (.002, -.001, -.001), .002),
        voltage=VoltageMeasurementErrors((1.02, 1.02), (.005, -.005), .005),
        frame=FrameErrors(np.deg2rad(2)), timing=TimingErrors(1, 1),
        actuation=ActuationErrors(.03, .05), drift=OperatingDrift(1.2))
    strong = DriveNonidealities(current=CurrentMeasurementErrors((1.16, 1.14, 1.15), (.01, -.015, .005), .01),
        voltage=VoltageMeasurementErrors((1.12, 1.12), (.02, -.02), .02),
        frame=FrameErrors(np.deg2rad(6)), timing=TimingErrors(1, 1),
        actuation=ActuationErrors(.15, .10), drift=OperatingDrift(1.5))
    cells = [Scenario("ideal", "ideal", "baseline", IDEAL)]
    for family, field in (("current", "current"), ("voltage", "voltage"), ("angle", "frame"),
                           ("inverter", "actuation"), ("bus_sag", "actuation"), ("rs_drift", "drift")):
        for level, cfg in (("mild", mild), ("strong", strong)):
            component = getattr(cfg, field)
            if family == "inverter":
                component = replace(component, bus_sag_fraction=0)
            elif family == "bus_sag":
                component = replace(component, phase_sign_voltage_drop_v=0)
            cells.append(Scenario(f"{family}_{level}", family, level, replace(IDEAL, **{field: component})))
    cells.append(Scenario("timing_one_sample", "timing", "one_sample", replace(IDEAL, timing=mild.timing)))
    cells.extend((Scenario("combined_mild", "combined", "mild", mild),
                  Scenario("combined_strong", "combined", "strong", strong)))
    return tuple(cells)


def generate_motors(population):
    rng = np.random.default_rng(SEEDS[population])
    for motor_id in range(MOTOR_COUNTS[population]):
        plant = PMSMParameters(Rs=float(rng.uniform(.35, .65)), Ld=float(rng.uniform(.8e-3, 1.4e-3)),
            Lq=float(rng.uniform(.7e-3, 1.3e-3)), psi_f=float(rng.uniform(.015, .028)),
            J=float(rng.uniform(3e-4, 8e-4)), B=float(rng.uniform(.8e-4, 2.5e-4)))
        yield motor_id, plant, int(rng.integers(1, 2**31-3))


def commissioning_pair(plant, seed, errors):
    """Providers own the plant; existing decision interfaces see records only.

    Share initial records between one-shot/adaptive, including random noise.
    Cache mechanical records by BOTH excitation and electrical controller model.
    Rs operating drift is deliberately not applied to any commissioning stage.
    """
    ec = ExcitationConfig(current_noise_std_a=.01, voltage_noise_std_v=.01,
                          speed_noise_std_rad_s=.02, seed=seed)
    rc = RotatingExcitationConfig(q_voltage_base_v=5, current_noise_std_a=.01,
        voltage_noise_std_v=.01, speed_noise_std_rad_s=.02, seed=seed+1)
    mc = MechanicalExcitationConfig(dc_bus_voltage_v=24, seed=seed+2)
    e_cache, r_cache, m_cache = {}, {}, {}
    def locked(cfg):
        if cfg not in e_cache:
            e_cache[cfg] = simulate_locked_rotor_measurements(plant, cfg, errors)
        return e_cache[cfg]
    def rotating(cfg):
        if cfg not in r_cache:
            r_cache[cfg] = simulate_driven_rotor_measurements(plant, cfg, errors)
        return r_cache[cfg]
    def mechanical(cfg, controller):
        key = (cfg, tuple(vars(controller).values()))
        if key not in m_cache:
            m_cache[key] = simulate_mechanical_measurements(plant, controller, cfg, errors).measurements
        return m_cache[key]
    electrical = commission_from_measurements(locked(ec), rotating(rc), PRIOR.pole_pairs)
    full = None
    if electrical.quality.accepted:
        full = complete_commissioning(electrical, mechanical(mc, electrical.retuned_controller_parameters(PRIOR)))
    adaptive = run_adaptive_commissioning(locked, rotating, mechanical, PRIOR,
        standstill_config=ec, rotating_config=rc, mechanical_config=mc)
    standstill_ok = (electrical.electrical is not None and
        _standstill_quality(electrical.electrical, PRIOR.pole_pairs, QualityPolicy()).accepted)
    records = []
    for method, result, estimates in (
        ("one_shot", full, _estimates_one_shot(electrical, full)),
        ("adaptive", adaptive.full_commissioning, _estimates_adaptive(adaptive))):
        accepted = result is not None and result.quality.accepted
        reasons = (electrical.quality.rejection_reasons if full is None else full.quality.rejection_reasons)
        row = dict(method=method, standstill_accepted=bool(standstill_ok) if method == "one_shot" else
            any(a.stage == Stage.STANDSTILL and a.quality.accepted for a in adaptive.attempts),
            rotating_accepted=(electrical.flux is not None and not any(r.startswith("rotating.") for r in electrical.quality.rejection_reasons)
                and electrical.quality.estimator_failure is None) if method == "one_shot" else
                any(a.stage == Stage.ROTATING and a.quality.accepted for a in adaptive.attempts),
            electrical_accepted=electrical.quality.accepted if method == "one_shot" else
                any(a.stage == Stage.ROTATING and a.quality.accepted for a in adaptive.attempts),
            mechanical_accepted=bool(full is not None and full.mechanical.quality.accepted) if method == "one_shot" else
                any(a.stage == Stage.MECHANICAL and a.quality.accepted for a in adaptive.attempts),
            full_accepted=accepted, retry_count=0 if method == "one_shot" else
                len(adaptive.attempts)-sum(v > 0 for v in adaptive.attempt_counts.values()),
            estimator_failures=(int(electrical.quality.estimator_failure is not None) +
                int(full is not None and full.mechanical.quality.estimator_failure is not None)) if method == "one_shot" else
                sum(not a.estimator_succeeded for a in adaptive.attempts),
            state=("full_accepted" if accepted else "rejected") if method == "one_shot" else adaptive.state.value,
            terminal_reason=None if method == "one_shot" else adaptive.terminal_reason,
            reasons=";".join(reasons if method == "one_shot" else adaptive.attempts[-1].quality.rejection_reasons),
            **_error_fields(estimates, plant))
        counts = {"standstill": 1, "rotating": 1, "mechanical": int(full is not None)} if method == "one_shot" else adaptive.attempt_counts
        row.update({f"attempts_{k}": v for k, v in counts.items()})
        row["commissioning_outcome"] = ("accepted_accurate" if accepted and row["all_six_accurate"] else
            "accepted_inaccurate" if accepted else "rejected_accurate" if row["all_six_accurate"] else "rejected_inaccurate_or_unavailable")
        records.append((row, result))
    history = [dict(stage=a.stage.value, number=a.number, config=asdict(a.config),
        estimator_succeeded=a.estimator_succeeded,
        estimates=None if a.estimate is None else {n: float(getattr(a.estimate, n)) for n in NAMES if hasattr(a.estimate, n)},
        accepted=a.quality.accepted, reasons=a.quality.rejection_reasons,
        checks=[asdict(c) for c in a.quality.checks],
        diagnostics=None if a.diagnostics is None else asdict(a.diagnostics),
        decision=a.retry_decision, action=a.retry_action,
        next_config=None if a.next_config is None else asdict(a.next_config)) for a in adaptive.attempts]
    return records, history


def operation_metrics(sim):
    """M15 success convention, comparing currents/references in the TRUE frame."""
    finite = all(np.all(np.isfinite(sim[k])) for k in ("rpm", "id", "iq", "measured_id", "measured_iq", "voltage_magnitude"))
    if not finite:
        return dict(control_success=False, operation_status="nonfinite", control_speed_rmse_rpm=None,
                    control_iq_rmse_a=None, recovery_time_s=None)
    mapped = {**sim, "iq_ref": sim["iq_ref_true"]}
    metric = _performance_metrics(mapped)
    recovery = metric["disturbance_recovery_time_s"]
    post = sim["time"] >= sim["load_step_time"]
    command_norm = np.hypot(sim["command_voltage_d"], sim["command_voltage_q"])
    discrepancy = np.hypot(sim["voltage_d"]-sim["command_true_voltage_d"],
                           sim["voltage_q"]-sim["command_true_voltage_q"])
    return dict(operation_status="evaluated", control_speed_rmse_rpm=metric["post_step_speed_rmse_rpm"],
        control_iq_rmse_a=metric["post_step_iq_tracking_rmse_a"],
        max_speed_deviation_rpm=metric["max_post_step_speed_deviation_rpm"],
        recovery_time_s=float(recovery) if np.isfinite(recovery) else None,
        control_success=bool(metric["post_step_speed_rmse_rpm"] <= 10 and
            metric["post_step_iq_tracking_rmse_a"] <= .05 and np.isfinite(recovery) and recovery <= .1),
        true_id_rms_a=float(np.sqrt(np.mean(sim["id"][post]**2))),
        true_current_peak_a=float(np.max(np.hypot(sim["id"], sim["iq"]))),
        measured_current_peak_a=float(np.max(np.hypot(sim["measured_id"], sim["measured_iq"]))),
        controller_frame_iq_rmse_a=float(np.sqrt(np.mean((sim["feedback_iq"][post]-sim["iq_ref"][post])**2))),
        command_saturation_fraction=float(np.mean(sim["voltage_saturated"])),
        actual_bus_saturation_fraction=float(np.mean(sim["actual_bus_saturated"])),
        terminal_voltage_utilization=float(np.max(sim["voltage_magnitude"])/sim["actual_voltage_limit"]),
        command_voltage_utilization=float(np.max(command_norm)/sim["voltage_limit"]),
        terminal_command_discrepancy_rmse_v=float(np.sqrt(np.mean(discrepancy**2))),
        terminal_command_discrepancy_max_v=float(np.max(discrepancy)),
        nominal_bus_voltage_v=sim["dc_bus_voltage"], actual_bus_voltage_v=sim["actual_dc_bus_voltage"],
        final_speed_rpm=float(sim["rpm"][-1]))


def run_population(population):
    rows, histories, truth, traces, dynamic_rows = [], [], [], [], []
    for motor_id, plant, seed in generate_motors(population):
        print(f"{population}: motor {motor_id} starts", flush=True)
        commission_cache, control_cache = {}, {}
        for cell in scenarios():
            # Drift affects operation only; no duplicate historically identical fits.
            corrupted = replace(cell.errors, drift=OperatingDrift())
            for cfg in (IDEAL, corrupted):
                if cfg not in commission_cache:
                    try:
                        commission_cache[cfg] = commissioning_pair(plant, seed, cfg)
                    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
                        # Retain the complete cell/method/exposure even on provider failure.
                        commission_cache[cfg] = ([(dict(method=method, full_accepted=False,
                            all_six_available=False, all_six_accurate=False, retry_count=0,
                            commissioning_outcome="rejected_inaccurate_or_unavailable", state="provider_error",
                            reasons=str(exc)), None) for method in ("one_shot", "adaptive")], [])
            for exposure in EXPOSURES:
                cfg = IDEAL if exposure == "operation_only" else corrupted
                operating_errors = IDEAL if exposure == "commissioning_only" else cell.errors
                pairs, history = commission_cache[cfg]
                if exposure == "combined":
                    histories.append(dict(motor_id=motor_id, scenario=cell.name, attempts=history))
                for commissioning_row, result in pairs:
                    row = dict(motor_id=motor_id, seed=seed, scenario=cell.name, family=cell.family,
                        severity=cell.severity, exposure=exposure, **commissioning_row,
                        operation_rs_factor=operating_errors.drift.rs_factor,
                        commissioning_drift_applied=False, operation_status="commissioning_unavailable", control_success=None)
                    if result is not None and result.quality.accepted:
                        controller = result.retuned_controller_parameters(PRIOR)
                        key = (tuple(vars(controller).values()), operating_errors)
                        try:
                            if key not in control_cache:
                                sim = run_speed_foc_simulation(plant_params=plant, controller_params=controller,
                                    dt=40e-6, dc_bus_voltage=24, nonidealities=operating_errors)
                                control_cache[key] = (operation_metrics(sim), sim)
                            metrics, sim = control_cache[key]
                            row.update(metrics)
                            if motor_id == 0 and exposure == "operation_only" and row["method"] == "adaptive" and cell.name in ("ideal", "combined_mild", "combined_strong"):
                                traces.extend(dict(scenario=cell.name, time_s=float(sim["time"][k]+40e-6),
                                    speed_rpm=float(sim["rpm"][k]), true_iq_a=float(sim["iq"][k]),
                                    measured_iq_a=float(sim["measured_iq"][k]),
                                    true_id_a=float(sim["id"][k]), terminal_voltage_v=float(sim["voltage_magnitude"][k]),
                                    command_voltage_v=float(np.hypot(sim["command_voltage_d"][k], sim["command_voltage_q"][k])),
                                    terminal_limit_v=sim["actual_voltage_limit"]) for k in range(0, len(sim["time"]), 25))
                        except (ValueError, FloatingPointError, OverflowError) as exc:
                            row.update(operation_status="simulation_error", operation_error=str(exc), control_success=False)
                    rows.append(row)
            print(f"  {cell.name}: one/adaptive accepted {[r[0]['full_accepted'] for r in commission_cache[corrupted][0]]}", flush=True)
        ideal_pairs = commission_cache[IDEAL][0]
        truth.append(dict(motor_id=motor_id, seed=seed, commissioning_truth=asdict(plant),
                          operation_Rs={c.name: plant.Rs*c.errors.drift.rs_factor for c in scenarios()}))
        # Small representative M16 interaction; point prediction remains unchanged.
        if motor_id == 0:
            full = ideal_pairs[1][1]
            if full is not None and full.quality.accepted:
                steady = assess_operating_point(full, OperatingPointRequest(1000, .05, 24, 5))
                request = DynamicOperatingRequest(0, 1000, .05, float(steady.required_voltage_magnitude_v*np.sqrt(3)*1.04), 5, .6)
                prediction = assess_dynamic_operating_point(full, request)
                for cell in scenarios():
                    if cell.name not in ("ideal", "bus_sag_mild", "bus_sag_strong", "combined_mild", "combined_strong", "rs_drift_strong"):
                        continue
                    entry = dict(motor_id=motor_id, scenario=cell.name, **asdict(request),
                        quasi_steady_deadline_met=prediction.quasi_steady.quasi_steady_deadline_met,
                        prediction_success=prediction.controller.predicted_closed_loop_success,
                        nominal_voltage_margin_v=steady.required_voltage_magnitude_v*.04)
                    try:
                        sim = run_speed_foc_simulation(plant_params=plant, controller_params=full.retuned_controller_parameters(PRIOR),
                            dt=40e-6, simulation_time=.6, speed_ref_rpm=1000, load_step_time=0, load_step_torque=.05,
                            dc_bus_voltage=request.dc_bus_voltage_v, nonidealities=cell.errors)
                        actual = evaluate_controller_trace(sim, request, 40e-6)
                        entry.update(operation_status="evaluated", actual_success=actual.predicted_closed_loop_success,
                            actual_hold_completion_s=actual.hold_completion_time_s,
                            actual_final_speed_rpm=actual.trace[-1].speed_rpm,
                            actual_bus_voltage_v=sim["actual_dc_bus_voltage"],
                            actual_bus_saturation_fraction=float(np.mean(sim["actual_bus_saturated"])))
                    except (ValueError, FloatingPointError, OverflowError) as exc:
                        entry.update(operation_status="simulation_error", operation_error=str(exc), actual_success=None)
                    dynamic_rows.append(entry)
    return rows, histories, truth, traces, dynamic_rows


def summarize(rows):
    report = {}
    commission = [r for r in rows if r["exposure"] == "combined"]
    for method in ("one_shot", "adaptive"):
        sample = [r for r in commission if r["method"] == method]
        report[method] = dict(total=len(sample), accepted=sum(r["full_accepted"] for r in sample),
            acceptance_coverage=sum(r["full_accepted"] for r in sample)/len(sample),
            stage_acceptance={stage: sum(bool(r.get(f"{stage}_accepted")) for r in sample)
                              for stage in ("standstill", "rotating", "electrical", "mechanical")},
            estimator_failures=sum(r.get("estimator_failures", 0) for r in sample),
            outcomes=dict(Counter(r["commissioning_outcome"] for r in sample)),
            all_six_available=sum(r["all_six_available"] for r in sample),
            silent_inaccurate_acceptance=sum(r["full_accepted"] and not r["all_six_accurate"] for r in sample),
            accurate_rejections=sum(not r["full_accepted"] and r["all_six_accurate"] for r in sample),
            retries=sum(r["retry_count"] for r in sample),
            states=dict(Counter(r["state"] for r in sample)),
            design_bound_terminations=sum("design_limit" in (r.get("terminal_reason") or "") for r in sample),
            residual_terminations=sum("model_residual_terminal" in (r.get("terminal_reason") or "") for r in sample))
    one = {(r["motor_id"], r["scenario"]): r for r in commission if r["method"] == "one_shot"}
    adaptive = [r for r in commission if r["method"] == "adaptive"]
    report["recovered_by_retry"] = sum(r["full_accepted"] and not one[r["motor_id"], r["scenario"]]["full_accepted"] for r in adaptive)
    report["retry_accepted_but_inaccurate"] = sum(r["retry_count"] > 0 and r["full_accepted"] and not r["all_six_accurate"] for r in adaptive)
    report["operation"] = {}
    for method in ("one_shot", "adaptive"):
        for exposure in EXPOSURES:
            sample = [r for r in rows if r["method"] == method and r["exposure"] == exposure]
            speed = [r["control_speed_rmse_rpm"] for r in sample if r.get("control_speed_rmse_rpm") is not None]
            report["operation"][f"{method}.{exposure}"] = dict(total=len(sample),
                evaluated=sum(r["control_success"] is not None for r in sample),
                successes=sum(r["control_success"] is True for r in sample),
                failures=sum(r["control_success"] is False for r in sample),
                unavailable=sum(r["control_success"] is None for r in sample),
                median_speed_rmse_rpm=float(np.median(speed)) if speed else None,
                worst_speed_rmse_rpm=max(speed) if speed else None)
    report["total_rows"] = len(rows)
    report["note"] = "Acceptance counts use one commissioning row per motor/scenario/method; exposure rows are not independent plants. Six-parameter <=10% labels are post-hoc only."
    return report


def plot_results(rows, traces, population):
    import matplotlib.pyplot as plt
    names = [c.name for c in scenarios()]
    metrics = ("error_Rs_percent", "error_Ld_percent", "error_Lq_percent", "error_psi_f_percent", "error_J_percent", "error_B_percent")
    values = []
    for name in names:
        sample = [r for r in rows if r["scenario"] == name and r["method"] == "adaptive" and r["exposure"] == "combined"]
        values.append([float(np.median(v)) if v else np.nan for key in metrics
            for v in [[r[key] for r in sample if r.get(key) is not None]]])
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), gridspec_kw={"width_ratios": [3, 1]})
    mesh = axes[0].imshow(np.ma.masked_invalid(values), aspect="auto", vmin=0, vmax=20, cmap="magma")
    axes[0].set_facecolor("#dddddd")
    axes[0].set_yticks(range(len(names)), names)
    axes[0].set_xticks(range(6), NAMES)
    axes[0].set_title("Adaptive median parameter error [%]; grey = unavailable")
    fig.colorbar(mesh, ax=axes[0], label="Absolute error [%]; color clipped at 20%")
    for i, name in enumerate(names):
        sample = [r for r in rows if r["scenario"] == name and r["method"] == "adaptive" and r["exposure"] == "combined"]
        axes[1].text(0, i, f"A {sum(r['full_accepted'] for r in sample)}/{len(sample)}; silent {sum(r['full_accepted'] and not r['all_six_accurate'] for r in sample)}", va="center", fontsize=9)
    axes[1].set(ylim=(len(names)-.5, -.5), xlim=(0, 1), title="Accept / silent counts")
    axes[1].axis("off")
    fig.suptitle(f"M17 {population}: frozen gates, structured bias not noise metadata")
    fig.tight_layout()
    fig.savefig(OUTPUT/f"{population}_nonideality_impact_matrix.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for name, color in zip(("ideal", "combined_mild", "combined_strong"), ("tab:blue", "tab:orange", "tab:green")):
        sample = [r for r in traces if r["scenario"] == name]
        if not sample:
            continue
        t = [r["time_s"] for r in sample]
        axes[0].plot(t, [r["speed_rpm"] for r in sample], label=name, color=color)
        axes[1].plot(t, [r["true_iq_a"] for r in sample], label=name+" true iq", color=color)
        axes[1].plot(t, [r["measured_iq_a"] for r in sample], linestyle=":", alpha=.6, color=color)
        axes[2].plot(t, [r["terminal_voltage_v"] for r in sample], label=name+" terminal", color=color)
        axes[2].plot(t, [r["command_voltage_v"] for r in sample], linestyle=":", alpha=.6, color=color)
    for ax, ylabel in zip(axes, ("Speed [rpm]", "Current [A]", "Voltage magnitude [V]")):
        ax.set_ylabel(ylabel)
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    axes[0].axvline(.3, color="black", linestyle=":")
    axes[-1].set_xlabel("Post-step observation time [s]")
    fig.suptitle(f"{population} motor 0: clean commissioning, combined OPERATING errors\nDotted curves: measured current / commanded voltage; solid: true current / terminal voltage")
    fig.tight_layout()
    fig.savefig(OUTPUT/f"{population}_combined_case_response.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", choices=SEEDS, required=True)
    args = parser.parse_args()
    matplotlib.use("Agg")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/"scenario_definitions.json").write_text(json.dumps([asdict(c) for c in scenarios()], indent=2), encoding="utf-8")
    rows, history, truth, traces, dynamics = run_population(args.population)
    name = "development" if args.population == "development" else "held_out"
    write_csv(OUTPUT/f"{name}.csv", rows)
    write_csv(OUTPUT/f"{name}_response_traces.csv", traces)
    write_csv(OUTPUT/f"{name}_m16_comparison.csv", dynamics)
    report = summarize(rows)
    report["population_seed"] = SEEDS[args.population]
    report["motors"] = MOTOR_COUNTS[args.population]
    report["m16"] = dict(cases=len(dynamics), agreement=sum(r["prediction_success"] == r["actual_success"] for r in dynamics),
        unavailable=sum(r["actual_success"] is None for r in dynamics),
        false_predicted_success=sum(r["prediction_success"] and r["actual_success"] is False for r in dynamics),
        false_predicted_failure=sum(not r["prediction_success"] and r["actual_success"] is True for r in dynamics))
    for suffix, data in (("summary", report), ("attempts", history), ("truth_audit", truth)):
        (OUTPUT/f"{name}_{suffix}.json").write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    plot_results(rows, traces, name)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
