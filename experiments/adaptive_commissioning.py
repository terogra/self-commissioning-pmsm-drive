"""Development and held-out evaluation of bounded commissioning retries.

Only this evaluation layer owns plant truth and post-hoc error/control labels.
The supervisor receives callbacks returning sampled measurements, never truth.
"""

import argparse
import csv
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

import matplotlib
import numpy as np

from experiments.commissioning_recovery import _performance_metrics
from src.adaptive_commissioning import RetryPolicy, Stage, run_adaptive_commissioning
from src.commissioning import commission_from_measurements
from src.commissioning_quality import QualityPolicy
from src.full_commissioning import complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.mechanical_identification import MechanicalQualityPolicy
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation


SEEDS = {"development": 20261031, "evaluation": 20261101}
NAMES = ("Rs", "Ld", "Lq", "psi_f", "J", "B")
PRIOR = PMSMParameters(Rs=.24, Ld=.0006, Lq=.0014, psi_f=.035, J=.0002, B=.0001)
# Predeclared cells are repeated with independently drawn plants at both seeds.
SCENARIOS = (
    "normal_low", "weak_electrical", "weak_flux", "weak_mechanical",
    "combined_weak", "medium_noise", "high_noise", "zero_standstill",
    "voltage_infeasible",
)


@dataclass(frozen=True)
class Case:
    name: str
    seed: int
    plant: PMSMParameters
    standstill: ExcitationConfig
    rotating: RotatingExcitationConfig
    mechanical: MechanicalExcitationConfig
    operating_request: OperatingPointRequest


def generate_cases(population):
    rng = np.random.default_rng(SEEDS[population])
    cases = []
    for name in SCENARIOS:
        plant = PMSMParameters(
            Rs=float(rng.uniform(.35, .65)), Ld=float(rng.uniform(.8e-3, 1.4e-3)),
            Lq=float(rng.uniform(.7e-3, 1.3e-3)), psi_f=float(rng.uniform(.015, .028)),
            J=float(rng.uniform(3e-4, 8e-4)), B=float(rng.uniform(.8e-4, 2.5e-4)),
        )
        seed = int(rng.integers(1, 2**31 - 1))
        noise = ("high" if name == "high_noise" else "medium" if name == "medium_noise" else "low")
        current = {"low": .01, "medium": .04, "high": .2}[noise]
        voltage = {"low": .01, "medium": .03, "high": .1}[noise]
        speed = {"low": .02, "medium": .1, "high": .4}[noise]
        mechanical_speed = {"low": .05, "medium": .2, "high": 1.0}[noise]
        bus = 12.0 if name == "voltage_infeasible" else 24.0
        e_scale = 0 if name == "zero_standstill" else .08 if name in ("weak_electrical", "combined_weak") else 1.0
        m_scale = .08 if name in ("weak_mechanical", "combined_weak") else 1.0
        weak_flux = name in ("weak_flux", "combined_weak")
        standstill = ExcitationConfig(d_voltage_v=1.2*e_scale, q_voltage_v=1.4*e_scale,
            dc_bus_voltage_v=bus, current_noise_std_a=current, voltage_noise_std_v=voltage,
            speed_noise_std_rad_s=speed, seed=seed)
        rotating = RotatingExcitationConfig(speed_rpm=120 if weak_flux else 600,
            q_voltage_base_v=5.0, dc_bus_voltage_v=bus,
            current_noise_std_a=.1 if weak_flux else current,
            voltage_noise_std_v=.1 if weak_flux else voltage,
            speed_noise_std_rad_s=.5 if weak_flux else speed, seed=seed+1)
        base = MechanicalExcitationConfig().iq_plateaus_a
        mechanical = MechanicalExcitationConfig(iq_plateaus_a=tuple(v*m_scale for v in base),
            dc_bus_voltage_v=bus, current_noise_std_a=current,
            speed_noise_std_rad_s=mechanical_speed, seed=seed+2)
        request = OperatingPointRequest(2000 if name == "voltage_infeasible" else 1000,
                                        .05, bus, 5)
        cases.append(Case(name, seed, plant, standstill, rotating, mechanical, request))
    return cases


def _estimates_one_shot(electrical, full):
    return {"standstill": electrical.electrical, "rotating": electrical.flux,
            "mechanical": None if full is None else full.mechanical.estimate}


def _estimates_adaptive(result):
    return {stage.value: next((a.estimate for a in reversed(result.attempts)
                               if a.stage == stage and a.estimate is not None), None)
            for stage in Stage}


def _error_fields(estimates, plant):
    values = {}
    for stage, names in (("standstill", NAMES[:3]), ("rotating", NAMES[3:4]),
                         ("mechanical", NAMES[4:])):
        estimate = estimates[stage]
        for name in names:
            value = None if estimate is None else float(getattr(estimate, name))
            values[f"estimate_{name}"] = value
            values[f"error_{name}_percent"] = None if value is None else 100*abs(value/getattr(plant, name)-1)
    values["all_six_available"] = all(values[f"error_{name}_percent"] is not None for name in NAMES)
    values["all_six_accurate"] = (values["all_six_available"]
        and all(values[f"error_{name}_percent"] <= 10 for name in NAMES))
    values["electrical_accurate"] = (all(values[f"error_{name}_percent"] is not None for name in NAMES[:4])
        and all(values[f"error_{name}_percent"] <= 10 for name in NAMES[:4]))
    values["mechanical_accurate"] = (all(values[f"error_{name}_percent"] is not None for name in NAMES[4:])
        and all(values[f"error_{name}_percent"] <= 10 for name in NAMES[4:]))
    return values


def _control_metrics(case, result):
    # Post-decision validation only. Never passed to run_adaptive_commissioning.
    if result is None or not result.quality.accepted:
        return {"control_postload_speed_rmse_rpm": None,
                "control_postload_iq_rmse_a": None, "control_recovery_time_s": None,
                "control_success": None}
    sim = run_speed_foc_simulation(plant_params=case.plant, controller_params=PRIOR,
        commissioning_result=result, dc_bus_voltage=case.operating_request.dc_bus_voltage_v,
        speed_ref_rpm=case.operating_request.speed_rpm,
        load_step_torque=case.operating_request.load_torque_nm,
        current_limit_a=case.operating_request.current_limit_a, dt=40e-6)
    metrics = _performance_metrics(sim)
    recovery = metrics["disturbance_recovery_time_s"]
    return {"control_postload_speed_rmse_rpm": metrics["post_step_speed_rmse_rpm"],
            "control_postload_iq_rmse_a": metrics["post_step_iq_tracking_rmse_a"],
            "control_recovery_time_s": None if not np.isfinite(recovery) else recovery,
            "control_success": bool(metrics["post_step_speed_rmse_rpm"] <= 10
                and metrics["post_step_iq_tracking_rmse_a"] <= .05
                and np.isfinite(recovery) and recovery <= .1)}


def run_case(case, retry_policy=RetryPolicy()):
    # Reuse the exact initial sampled data for both paths, including noise.
    standstill_cache, rotating_cache, mechanical_cache = {}, {}, {}

    def standstill(config):
        if config not in standstill_cache:
            standstill_cache[config] = simulate_locked_rotor_measurements(case.plant, config)
        return standstill_cache[config]

    def rotating(config):
        if config not in rotating_cache:
            rotating_cache[config] = simulate_driven_rotor_measurements(case.plant, config)
        return rotating_cache[config]

    def mechanical(config, controller):
        if config not in mechanical_cache:
            mechanical_cache[config] = simulate_mechanical_measurements(case.plant, controller, config).measurements
        return mechanical_cache[config]

    one_electrical = commission_from_measurements(
        standstill(case.standstill), rotating(case.rotating), PRIOR.pole_pairs)
    one_full = None
    if one_electrical.quality.accepted:
        controller = one_electrical.retuned_controller_parameters(PRIOR)
        one_full = complete_commissioning(one_electrical, mechanical(case.mechanical, controller))
    adaptive = run_adaptive_commissioning(
        standstill, rotating, mechanical, PRIOR,
        standstill_config=case.standstill, rotating_config=case.rotating,
        mechanical_config=case.mechanical, retry_policy=retry_policy,
        operating_request=case.operating_request,
    )
    one_accepted = one_full is not None and one_full.quality.accepted
    one_feasibility = assess_operating_point(one_full, case.operating_request) if one_accepted else None
    result = []
    for method, electrical_ok, mechanical_ok, full, feasibility, estimates in (
        ("one_shot", one_electrical.quality.accepted,
         False if one_full is None else one_full.mechanical.quality.accepted,
         one_full, one_feasibility, _estimates_one_shot(one_electrical, one_full)),
        ("adaptive", any(a.stage == Stage.ROTATING and a.quality.accepted for a in adaptive.attempts),
         any(a.stage == Stage.MECHANICAL and a.quality.accepted for a in adaptive.attempts),
         adaptive.full_commissioning, adaptive.operating_feasibility, _estimates_adaptive(adaptive)),
    ):
        accepted = full is not None and full.quality.accepted
        # Control is evaluated only for accepted, predicted feasible cases.
        control = _control_metrics(case, full if accepted and feasibility.steady_state_feasible else None)
        row = {"case": case.name, "seed": case.seed, "method": method,
               "electrical_accepted": bool(electrical_ok), "mechanical_accepted": bool(mechanical_ok),
               "full_accepted": bool(accepted),
               "attempts_standstill": 1 if method == "one_shot" else adaptive.attempt_counts["standstill"],
               "attempts_rotating": 1 if method == "one_shot" else adaptive.attempt_counts["rotating"],
               "attempts_mechanical": (int(one_full is not None) if method == "one_shot" else adaptive.attempt_counts["mechanical"]),
               "retry_count": (0 if method == "one_shot" else len(adaptive.attempts)-sum(
                   adaptive.attempt_counts[s] > 0 for s in adaptive.attempt_counts)),
               "state": ("full_accepted" if accepted else "rejected") if method == "one_shot" else adaptive.state.value,
               "reasons": ("; ".join(one_electrical.quality.rejection_reasons if one_full is None
                                    else one_full.quality.rejection_reasons)
                           if method == "one_shot" else "; ".join(adaptive.attempts[-1].quality.rejection_reasons)),
               "terminal_reason": None if method == "one_shot" else adaptive.terminal_reason,
               "operating_feasible": None if feasibility is None else feasibility.steady_state_feasible,
               "voltage_margin_v": None if feasibility is None else feasibility.voltage_margin_v,
               "current_margin_a": None if feasibility is None else feasibility.current_margin_a,
               "bus_voltage_v": case.operating_request.dc_bus_voltage_v,
               **_error_fields(estimates, case.plant), **control}
        result.append(row)
    history = []
    for a in adaptive.attempts:
        history.append({"case": case.name, "stage": a.stage.value, "attempt": a.number,
                        "configuration": asdict(a.config), "estimator_succeeded": a.estimator_succeeded,
                        "quality_accepted": a.quality.accepted,
                        "reasons": list(a.quality.rejection_reasons),
                        "checks": [asdict(c) for c in a.quality.checks],
                        "diagnostics": None if a.diagnostics is None else asdict(a.diagnostics),
                        "retry_decision": a.retry_decision, "retry_action": a.retry_action,
                        "next_configuration": None if a.next_config is None else asdict(a.next_config)})
    truth = {"case": case.name, "seed": case.seed, **{name: getattr(case.plant, name) for name in NAMES}}
    return result, history, truth


def summarize(rows):
    summary = {}
    for method in ("one_shot", "adaptive"):
        sample = [r for r in rows if r["method"] == method]
        accepted = [r for r in sample if r["full_accepted"]]
        scorable = [r for r in sample if r["all_six_available"]]
        accurate = [r for r in scorable if r["all_six_accurate"]]
        inaccurate = [r for r in scorable if not r["all_six_accurate"]]
        false_accept = sum(not r["all_six_accurate"] for r in accepted)
        false_reject = sum(not r["full_accepted"] for r in accurate)
        summary[method] = {
            "total": len(sample), "accepted": len(accepted), "acceptance_coverage": len(accepted)/len(sample),
            "accurate_accepted": sum(r["all_six_accurate"] for r in accepted),
            "false_acceptance_count": false_accept,
            "false_acceptance_fraction_of_accepted": false_accept/len(accepted) if accepted else None,
            "false_rejection_count": false_reject,
            "false_rejection_fraction_of_accurate_complete": false_reject/len(accurate) if accurate else None,
            "six_parameter_scorable": len(scorable),
            "six_parameter_unscorable": len(sample)-len(scorable),
            "inaccurate_complete": len(inaccurate),
            "electrical_acceptance": sum(r["electrical_accepted"] for r in sample),
            "mechanical_acceptance": sum(r["mechanical_accepted"] for r in sample),
            "operating_infeasible": sum(r["operating_feasible"] is False for r in sample),
            "control_evaluated": sum(r["control_success"] is not None for r in sample),
            "control_success": sum(r["control_success"] is True for r in sample),
            "parameter_errors_percent": {name: {
                "median": float(np.median(v)) if v else None,
                "worst": float(max(v)) if v else None, "n": len(v)}
                for name in NAMES for v in [[r[f"error_{name}_percent"] for r in sample
                                             if r[f"error_{name}_percent"] is not None]]},
        }
    one = {r["case"]: r for r in rows if r["method"] == "one_shot"}
    adaptive = [r for r in rows if r["method"] == "adaptive"]
    summary["comparison"] = {
        "recovered_by_retry": sum(r["full_accepted"] and not one[r["case"]]["full_accepted"] for r in adaptive),
        "retries_per_successful_case": [r["retry_count"] for r in adaptive if r["full_accepted"]],
        "retry_budget_exhausted": sum(r["state"] == "retry_budget_exhausted" for r in adaptive),
        "non_retryable_rejected": sum(r["state"] == "terminal_rejected" for r in adaptive),
        "accepted_but_operating_infeasible": sum(r["full_accepted"] and r["operating_feasible"] is False
                                                   for r in adaptive),
    }
    return summary


def save_results(rows, histories, truth, population, output_dir):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "attempts.json").write_text(json.dumps(histories, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "truth_posthoc.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    summary = summarize(rows)
    summary["methodology"] = {"population": population, "seed": SEEDS[population],
        "scenarios": SCENARIOS, "retry_policy": asdict(RetryPolicy()),
        "electrical_quality_policy": asdict(QualityPolicy()),
        "mechanical_quality_policy": asdict(MechanicalQualityPolicy()),
        "accuracy_label": "All six available parameter errors <= 10%; truth used post-hoc only",
        "unscorable": "Missing estimates retained; excluded from conditional false-rejection denominator",
        "control": "Only accepted and predicted feasible cases simulated; unavailable otherwise"}
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    reasons = {}
    for attempt in histories:
        for reason in attempt["reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    (output_dir / "retry_reasons.json").write_text(json.dumps(reasons, indent=2), encoding="utf-8")
    example = [a for a in histories if a["case"] == "combined_weak"]
    (output_dir / "example_trace.json").write_text(json.dumps({
        "case": "combined_weak", "final_state": next(r["state"] for r in rows
            if r["case"] == "combined_weak" and r["method"] == "adaptive"),
        "attempts": [{"stage": a["stage"], "number": a["attempt"],
                      "reasons": a["reasons"], "decision": a["retry_decision"],
                      "action": a["retry_action"]} for a in example],
    }, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(12, max(3.5, .5 * len(reasons) + 1)))
    ordered = sorted(reasons.items(), key=lambda pair: (-pair[1], pair[0]))
    ax.barh([key for key, _ in ordered][::-1], [value for _, value in ordered][::-1],
            color="tab:orange")
    ax.set_xlabel("Rejected attempt count")
    ax.set_title("Measured-data rejection reasons", fontsize=11)
    ax.grid(axis="x", alpha=.25)
    fig.subplots_adjust(left=.58, right=.97, top=.90, bottom=.15)
    fig.savefig(output_dir / "retry_reasons.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    adaptive = [r for r in rows if r["method"] == "adaptive"]
    labels = [r["case"] for r in adaptive]
    for j, stage in enumerate(("standstill", "rotating", "mechanical")):
        values = [r[f"attempts_{stage}"] for r in adaptive]
        left = np.arange(len(labels))
        ax.bar(left, values, bottom=[sum(row[f"attempts_{s}"] for s in
               ("standstill", "rotating", "mechanical")[:j]) for row in adaptive], label=stage)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=35, ha="right")
    ax.set_ylabel("Attempts (stacked by stage)")
    ax.legend()
    ax.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(output_dir / "attempts_to_acceptance.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    for ax, name in zip(axes.flat, NAMES):
        groups, labels = [], []
        for method in ("one_shot", "adaptive"):
            for accepted in (True, False):
                vals = [r[f"error_{name}_percent"] for r in rows if r["method"] == method
                        and r["full_accepted"] == accepted and r[f"error_{name}_percent"] is not None]
                if vals:
                    groups.append(vals)
                    labels.append(f"{method}\n{'accepted' if accepted else 'rejected'}\nn={len(vals)}")
        if groups:
            ax.boxplot(groups, tick_labels=labels)
            ax.set_yscale("log")
        ax.axhline(10, color="tab:red", linestyle="--", linewidth=1)
        ax.set_title(name)
        ax.set_ylabel("Absolute error [%]")
        ax.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(output_dir / "parameter_error_by_decision.png", dpi=160)
    plt.close(fig)
    return summary


def run_population(population, output_dir=None):
    rows, histories, truth = [], [], []
    for case in generate_cases(population):
        try:
            case_rows, case_history, case_truth = run_case(case)
        except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            # Preserve unexpected failures as explicit rows, never silently skip.
            case_rows = []
            for method in ("one_shot", "adaptive"):
                case_rows.append({"case": case.name, "seed": case.seed, "method": method,
                    "electrical_accepted": False, "mechanical_accepted": False,
                    "full_accepted": False, "attempts_standstill": 0,
                    "attempts_rotating": 0, "attempts_mechanical": 0, "retry_count": 0,
                    "state": "evaluation_error", "reasons": str(exc), "terminal_reason": str(exc),
                    "operating_feasible": None, "voltage_margin_v": None, "current_margin_a": None,
                    "bus_voltage_v": case.operating_request.dc_bus_voltage_v,
                    **_error_fields({"standstill": None, "rotating": None, "mechanical": None}, case.plant),
                    **_control_metrics(case, None)})
            case_history = [{"case": case.name, "evaluation_error": str(exc)}]
            case_truth = {"case": case.name, **{name: getattr(case.plant, name) for name in NAMES}}
        rows.extend(case_rows)
        histories.extend(case_history)
        truth.append(case_truth)
    summary = save_results(rows, histories, truth, population,
                           output_dir or Path("results/adaptive_commissioning") / population)
    return rows, histories, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", choices=tuple(SEEDS), required=True)
    args = parser.parse_args()
    _, _, summary = run_population(args.population)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
