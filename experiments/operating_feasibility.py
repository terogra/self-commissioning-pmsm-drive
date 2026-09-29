"""Compare commissioned id=0 predictions with independent simulated outcomes."""

import csv
from dataclasses import asdict, replace
import json
from pathlib import Path

import matplotlib
import numpy as np

from experiments.mechanical_population import generate_mechanical_cases
from src.commissioning import commission_from_measurements
from src.full_commissioning import complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point, operating_envelope, _evaluate_id_zero
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation


EVALUATION_SEED = 20261021
PRIOR = PMSMParameters(Rs=0.24, Ld=0.6e-3, Lq=1.4e-3, psi_f=0.035)
SCENARIOS = ("low_speed", "current_limited", "both_limited", "voltage_limited",
             "boundary_inside", "boundary_outside", "acceleration_limited")


def commission_plant(plant, electrical_seed=101, mechanical_config=MechanicalExcitationConfig()):
    """Only data generation sees the plant. The estimator interfaces are unchanged."""
    locked = simulate_locked_rotor_measurements(plant, ExcitationConfig(
        current_noise_std_a=0.01, voltage_noise_std_v=0.01, speed_noise_std_rad_s=0.02, seed=electrical_seed))
    rotating = simulate_driven_rotor_measurements(plant, RotatingExcitationConfig(
        q_voltage_base_v=5, current_noise_std_a=0.01, voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.02, seed=electrical_seed+1))
    electrical = commission_from_measurements(locked, rotating, PRIOR.pole_pairs)
    data = None
    if electrical.quality.accepted:
        data = simulate_mechanical_measurements(plant, electrical.retuned_controller_parameters(PRIOR), mechanical_config).measurements
    return complete_commissioning(electrical, data)


def oracle_prediction(plant, request):
    """Evaluation-only reference; deliberately separate from normal accepted API."""
    return _evaluate_id_zero(Rs=plant.Rs, Lq=plant.Lq, psi_f=plant.psi_f,
                             B=plant.B, pole_pairs=plant.pole_pairs, request=request)


def dynamic_metrics(simulation):
    """Outcome uses simulated signals only, not the analytical prediction.

    Success: all final 0.1 s speed samples within max(1 rpm, 1% command),
    and final-window current magnitude no more than 1.01 times design limit.
    It describes reaching/holding the target within the specified run duration.
    """
    t = simulation["time"]
    terminal = t >= t[-1] - 0.1
    post = t >= simulation["load_step_time"]
    error = simulation["rpm"]-simulation["speed_ref_rpm"]
    current = np.hypot(simulation["id"], simulation["iq"])
    tolerance = max(1.0, 0.01*simulation["speed_ref_rpm"])
    finite = all(np.all(np.isfinite(simulation[k])) for k in ("rpm", "id", "iq", "voltage_magnitude"))
    success = bool(finite and np.max(np.abs(error[terminal])) <= tolerance
                   and np.max(current[terminal]) <= 1.01*simulation["current_limit_a"])
    return {
        "closed_loop_dynamic_success": success,
        "achieved_speed_rpm": float(np.mean(simulation["rpm"][terminal])),
        "terminal_max_speed_error_rpm": float(np.max(np.abs(error[terminal]))),
        "speed_rmse_rpm": float(np.sqrt(np.mean(error**2))),
        "post_load_speed_rmse_rpm": float(np.sqrt(np.mean(error[post]**2))),
        "terminal_current_magnitude_a": float(np.mean(current[terminal])),
        "terminal_max_current_magnitude_a": float(np.max(current[terminal])),
        "terminal_iq_tracking_rmse_a": float(np.sqrt(np.mean((simulation["iq"][terminal]-simulation["iq_ref"][terminal])**2))),
        "saturation_fraction": float(np.mean(simulation["voltage_saturated"])),
        "terminal_saturation_fraction": float(np.mean(simulation["voltage_saturated"][terminal])),
        "terminal_applied_voltage_v": float(np.mean(simulation["voltage_magnitude"][terminal])),
        "maximum_applied_voltage_v": float(np.max(simulation["voltage_magnitude"])),
    }


def simulate_request(plant, commissioned, request, duration=0.6):
    return run_speed_foc_simulation(plant_params=plant, controller_params=PRIOR,
        commissioning_result=commissioned, speed_ref_rpm=request.speed_rpm,
        load_step_torque=request.load_torque_nm, load_step_time=0.3, simulation_time=duration,
        dc_bus_voltage=request.dc_bus_voltage_v, current_limit_a=request.current_limit_a, dt=40e-6)


def validation_requests(full):
    # Boundary positions are specified from estimates before any control run.
    nominal = assess_operating_point(full, OperatingPointRequest(1000, 0.05, 48, 5))
    bus_boundary = np.sqrt(3)*nominal.required_voltage_magnitude_v
    slow = assess_operating_point(full, OperatingPointRequest(1000, 0.005, 48, 5))
    return dict(zip(SCENARIOS, (
        OperatingPointRequest(250, 0.02, 24, 3),
        OperatingPointRequest(250, 0.5, 48, 1),
        OperatingPointRequest(2500, 0.5, 12, 1),
        OperatingPointRequest(2000, 0.05, 12, 5),
        OperatingPointRequest(1000, 0.05, float(bus_boundary*1.005), 5),
        OperatingPointRequest(1000, 0.05, float(bus_boundary*0.995), 5),
        OperatingPointRequest(1000, 0.005, 48, slow.required_current_magnitude_a*1.10),
    )))


def compare_case(plant, full, request, **metadata):
    prediction = assess_operating_point(full, request)
    oracle = oracle_prediction(plant, request)
    simulation = simulate_request(plant, full, request)
    metrics = dynamic_metrics(simulation)
    row = {**metadata, "status": "evaluated", **asdict(request),
           "electrical_accepted": full.electrical.quality.accepted,
           "mechanical_accepted": full.mechanical.quality.accepted,
           **{k: v for k, v in asdict(prediction).items() if k not in ("assumptions", "reasons")},
           "classification": prediction.classification, "reasons": "; ".join(prediction.reasons),
           "oracle_steady_state_feasible": oracle.feasible, **metrics,
           "extended_run_success": None, "extended_achieved_speed_rpm": None}
    if prediction.feasible and not metrics["closed_loop_dynamic_success"]:
        # Predeclared investigation, same request/controller, longer time only.
        extended = dynamic_metrics(simulate_request(plant, full, request, duration=4.0))
        row.update(extended_run_success=extended["closed_loop_dynamic_success"],
                   extended_achieved_speed_rpm=extended["achieved_speed_rpm"])
    return row, simulation


def confusion(rows):
    evaluated = [r for r in rows if r.get("status") == "evaluated"]
    return {"total_cases": len(rows), "evaluated_cases": len(evaluated),
            "unavailable_cases": len(rows)-len(evaluated),
            "true_positives": sum(r["steady_state_feasible"] and r["closed_loop_dynamic_success"] for r in evaluated),
            "true_negatives": sum(not r["steady_state_feasible"] and not r["closed_loop_dynamic_success"] for r in evaluated),
            "false_feasible": sum(r["steady_state_feasible"] and not r["closed_loop_dynamic_success"] for r in evaluated),
            "false_infeasible": sum(not r["steady_state_feasible"] and r["closed_loop_dynamic_success"] for r in evaluated),
            "oracle_prediction_agreement": sum(r["steady_state_feasible"] == r["oracle_steady_state_feasible"] for r in evaluated)}


def run_held_out():
    rng = np.random.default_rng(EVALUATION_SEED)
    rows, plants = [], []
    for motor_id in range(3):
        plant = PMSMParameters(Rs=float(rng.uniform(.35, .65)), Ld=float(rng.uniform(.8e-3, 1.4e-3)),
            Lq=float(rng.uniform(.7e-3, 1.3e-3)), psi_f=float(rng.uniform(.015, .028)),
            J=float(rng.uniform(3e-4, 8e-4)), B=float(rng.uniform(.8e-4, 2.5e-4)))
        seed = int(rng.integers(0, 2**31-3))
        full = commission_plant(plant, seed, MechanicalExcitationConfig(seed=seed+2))
        plants.append({"motor_id": motor_id, "seed": seed, "true": asdict(plant),
                       "accepted": full.quality.accepted, "reasons": full.quality.rejection_reasons,
                       "identified": asdict(full.retuned_controller_parameters(PRIOR)) if full.quality.accepted else None})
        if not full.quality.accepted:
            rows.extend({"motor_id": motor_id, "scenario": scenario, "status": "commissioning_unavailable",
                         "reasons": "; ".join(full.quality.rejection_reasons)} for scenario in SCENARIOS)
            continue
        for scenario, request in validation_requests(full).items():
            try:
                row, _ = compare_case(plant, full, request, motor_id=motor_id, scenario=scenario)
            except (ValueError, FloatingPointError, OverflowError) as exc:
                row = {"motor_id": motor_id, "scenario": scenario, "status": "evaluation_error", "reasons": str(exc)}
            rows.append(row)
    return rows, plants


def reanalyze_pr8():
    """Replay accepted measurement stages; reuse historical control outcomes.

    PR #8 CSV did not save electrical estimates. Never substitute its true
    electrical columns into the normal API. Reproduce the original sampled fits.
    """
    path = Path("results/mechanical_population/evaluation/cases.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        historical = list(csv.DictReader(handle))
    cases = {c.case_id: c for c in generate_mechanical_cases("evaluation")}
    rows = []
    for original in historical:
        case = cases[int(original["case_id"])]
        row = {"case_id": case.case_id, "original_status": original["status"],
               "commissioning_accepted": original["full_accepted"] == "True", "status": "commissioning_unavailable"}
        if not row["commissioning_accepted"]:
            rows.append(row)
            continue
        config = MechanicalExcitationConfig(
            iq_plateaus_a=tuple(case.excitation_scale*v for v in MechanicalExcitationConfig().iq_plateaus_a),
            current_noise_std_a=case.noise.current_std_a, speed_noise_std_rad_s=case.noise.speed_std_rad_s,
            dc_bus_voltage_v=case.dc_bus_voltage_v, seed=case.seed)
        full = commission_plant(case.plant, case.seed+1, config)
        if not full.quality.accepted:
            raise ValueError(f"Historical commissioning replay changed acceptance: {case.case_id}")
        for name in ("J", "B"):
            if not np.isclose(getattr(full.mechanical.estimate, name), float(original[f"estimate_{name}"]), rtol=1e-10):
                raise ValueError(f"Historical {name} replay differs: {case.case_id}")
        request = OperatingPointRequest(1000, 0.05, case.dc_bus_voltage_v, 5)
        prediction = assess_operating_point(full, request)
        oracle = oracle_prediction(case.plant, request)
        # Historical simulation-only criterion, without the former truth-error label.
        def historical_success(prefix):
            recovery = original[f"{prefix}_disturbance_recovery_time_s"]
            return (float(original[f"{prefix}_post_step_speed_rmse_rpm"]) <= 10
                    and float(original[f"{prefix}_post_step_iq_tracking_rmse_a"]) <= .05
                    and bool(recovery) and float(recovery) <= .10)
        row.update(status="evaluated", **asdict(prediction),
                   oracle_steady_state_feasible=oracle.feasible,
                   closed_loop_dynamic_success=historical_success("full commissioned"),
                   oracle_dynamic_success=historical_success("oracle"),
                   original_speed_rmse_rpm=float(original["full commissioned_post_step_speed_rmse_rpm"]),
                   original_saturation_fraction=float(original["full commissioned_saturation_fraction"]))
        rows.append(row)
    return rows


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path("results/operating_feasibility")
    output.mkdir(parents=True, exist_ok=True)
    plant = PMSMParameters(Rs=.56, Ld=.0014, Lq=.0008, psi_f=.015, J=.0005, B=.0003)
    full = commission_plant(plant)
    rows, simulations = [], {}
    for scenario, request in validation_requests(full).items():
        row, sim = compare_case(plant, full, request, scenario=scenario)
        rows.append(row)
        simulations[scenario] = sim
    write_csv(output / "representative.csv", rows)
    (output / "representative_model.json").write_text(json.dumps({
        "true_evaluation_only": asdict(plant), "identified": asdict(full.retuned_controller_parameters(PRIOR)),
        "electrical_accepted": full.electrical.quality.accepted, "mechanical_accepted": full.mechanical.quality.accepted,
        "assumptions": assess_operating_point(full, OperatingPointRequest(1000, .05, 24)).assumptions}, indent=2), encoding="utf-8")
    speeds, loads = np.linspace(0, 3000, 61), np.linspace(0, .5, 51)
    envelope = operating_envelope(full, speeds, loads, 24, 2)
    write_csv(output / "envelope.csv", [{**asdict(r), "classification": r.classification} for r in envelope])
    labels = ("feasible", "current_limited", "voltage_limited", "both_limited")
    from matplotlib.colors import ListedColormap, BoundaryNorm
    cmap = ListedColormap(["#3b9b67", "#e5b653", "#6795ca", "#ce605a"])
    fig, ax = plt.subplots(figsize=(9, 5))
    values = np.array([labels.index(r.classification) for r in envelope]).reshape(len(loads), len(speeds))
    mesh = ax.pcolormesh(speeds, loads, values, cmap=cmap, norm=BoundaryNorm(np.arange(5)-.5, 4), shading="nearest")
    fig.colorbar(mesh, ax=ax, ticks=range(4)).ax.set_yticklabels([s.replace("_", " ") for s in labels])
    ax.set(xlabel="Requested speed [rpm]", ylabel="External load [N m]", title="Commissioned id=0 steady-state envelope: 24 V, 2 A design limit")
    fig.tight_layout()
    fig.savefig(output / "envelope.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for scenario in ("low_speed", "boundary_inside", "voltage_limited", "acceleration_limited"):
        sim = simulations[scenario]
        axes[0].plot(sim["time"], sim["rpm"]/sim["speed_ref_rpm"], label=scenario)
        axes[1].plot(sim["time"], sim["voltage_magnitude"]/sim["voltage_limit"], label=scenario)
    axes[0].set_ylabel("Speed / command")
    axes[1].set_ylabel("Applied voltage / limit")
    for ax in axes:
        ax.axhline(1, linestyle=":", color="black")
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "representative_dynamics.png", dpi=160)
    plt.close(fig)
    retrospective = reanalyze_pr8()
    write_csv(output / "pr8_reanalysis.csv", retrospective)
    held_out, plants = run_held_out()
    write_csv(output / "held_out.csv", held_out)
    (output / "held_out_plants.json").write_text(json.dumps(plants, indent=2), encoding="utf-8")
    summary = {"evaluation_seed": EVALUATION_SEED, "representative": confusion(rows),
               "pr8_reanalysis": confusion(retrospective), "held_out": confusion(held_out),
               "outcome_criterion": "Final 0.1 s max speed error <= max(1 rpm, 1% command), max current <= 1.01 Imax in 0.6 s run",
               "retrospective_criterion": "Historical post-load speed RMSE <=10 rpm, iq RMSE <=0.05 A, recovery <=0.1 s; no true-parameter error label",
               "extended_run": "All false-feasible cases rerun for 4 s with unchanged request/controller; not used to relabel 0.6 s outcomes"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
