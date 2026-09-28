"""Reproducible, failure-preserving validation of offline commissioning."""

from collections import Counter
from dataclasses import dataclass
from math import hypot, isfinite, pi, sqrt

import numpy as np

from experiments.parameter_sensitivity import calculate_metrics
from src.commissioning import commission_from_measurements
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.motor import PMSMParameters
from src.rotating_identification import (
    RotatingExcitationConfig,
    simulate_driven_rotor_measurements,
)
from src.speed_foc_simulation import run_speed_foc_simulation


PARAMETERS = ("Rs", "Ld", "Lq", "psi_f")
DEFAULT_CONTROLLER = PMSMParameters(Rs=0.24, Ld=0.6e-3, Lq=1.4e-3, psi_f=0.035)


@dataclass(frozen=True)
class NoiseCondition:
    name: str
    current_std_a: float
    voltage_std_v: float
    speed_std_rad_s: float


@dataclass(frozen=True)
class MonteCarloConfig:
    seed: int = 20260929
    repeats: int = 2
    noise_conditions: tuple[NoiseCondition, ...] = (
        NoiseCondition("low", 0.01, 0.01, 0.02),
        NoiseCondition("medium", 0.08, 0.05, 0.05),
        NoiseCondition("high", 0.4, 0.2, 0.1),
    )
    commissioning_speeds_rpm: tuple[float, ...] = (0.0, 150.0, 600.0, 1200.0)
    dc_bus_voltages_v: tuple[float, ...] = (12.0, 24.0, 48.0)
    include_weak_excitation: bool = True
    control_dt_s: float = 40e-6
    excitation_scales: tuple[float, ...] = (1.0,)


@dataclass(frozen=True)
class CommissioningCase:
    case_id: int
    plant: PMSMParameters
    noise: NoiseCondition
    commissioning_speed_rpm: float
    dc_bus_voltage_v: float
    excitation_scale: float
    seed: int


def generate_cases(config: MonteCarloConfig = MonteCarloConfig()):
    """Stratify conditions and independently draw a plant for every cell/repeat."""
    if (not isinstance(config.repeats, int) or config.repeats < 1
            or not config.noise_conditions or not config.commissioning_speeds_rpm
            or not config.dc_bus_voltages_v or not config.excitation_scales):
        raise ValueError("Monte Carlo design needs positive repeats and nonempty conditions")
    if config.control_dt_s <= 0 or not isfinite(config.control_dt_s):
        raise ValueError("control_dt_s must be positive and finite")
    if any(not isfinite(v) or v <= 0 for v in config.dc_bus_voltages_v):
        raise ValueError("DC-bus voltages must be positive and finite")
    if any(not isfinite(v) or v < 0 for v in config.commissioning_speeds_rpm):
        raise ValueError("Commissioning speeds must be nonnegative and finite")
    if any(not isfinite(v) or v < 0 for v in config.excitation_scales):
        raise ValueError("Excitation scales must be nonnegative and finite")
    if any(not n.name or any(not isfinite(v) or v < 0 for v in (
        n.current_std_a, n.voltage_std_v, n.speed_std_rad_s
    )) for n in config.noise_conditions):
        raise ValueError("Noise conditions need names and nonnegative finite standard deviations")

    rng = np.random.default_rng(config.seed)
    cases = []
    for noise in config.noise_conditions:
        for speed in config.commissioning_speeds_rpm:
            for bus in config.dc_bus_voltages_v:
                for _ in range(config.repeats):
                    for scale in config.excitation_scales:
                        plant = PMSMParameters(
                            Rs=float(rng.uniform(0.25, 0.75)),
                            Ld=float(rng.uniform(0.65e-3, 1.55e-3)),
                            Lq=float(rng.uniform(0.60e-3, 1.50e-3)),
                            psi_f=float(rng.uniform(0.012, 0.036)),
                        )
                        cases.append(CommissioningCase(
                            len(cases), plant, noise, speed, bus, scale,
                            int(rng.integers(0, 2**31 - 1)),
                        ))
    if config.include_weak_excitation:
        # A deliberately unexcited locked-rotor run tests rank-failure handling.
        cases.append(CommissioningCase(
            len(cases), PMSMParameters(Rs=0.5, Ld=1.1e-3, Lq=0.9e-3, psi_f=0.024),
            NoiseCondition("none", 0.0, 0.0, 0.0), 600.0, 24.0, 0.0,
            int(rng.integers(0, 2**31 - 1)),
        ))
    return cases


def _metrics(simulation):
    common = calculate_metrics(simulation)
    post = simulation["time"] >= simulation["load_step_time"]
    return {
        "speed_rmse_rpm": float(np.sqrt(np.mean(
            (simulation["rpm"][post] - simulation["speed_ref_rpm"]) ** 2
        ))),
        "iq_tracking_rmse_a": float(np.sqrt(np.mean(
            (simulation["iq"][post] - simulation["iq_ref"][post]) ** 2
        ))),
        "recovery_time_s": common["disturbance_recovery_time_s"],
        "saturation_fraction": float(np.mean(simulation["voltage_saturated"])),
    }


def _voltage_feasibility(plant, bus_voltage, speed_ref_rpm=1000.0, load_torque=0.05):
    """Approximate steady-state id=0 feasibility at the post-step operating point."""
    omega = speed_ref_rpm * 2 * pi / 60
    iq = (load_torque + plant.B * omega) / (1.5 * plant.pole_pairs * plant.psi_f)
    omega_e = plant.pole_pairs * omega
    required_voltage = hypot(-omega_e * plant.Lq * iq,
                             plant.Rs * iq + omega_e * plant.psi_f)
    return required_voltage, required_voltage <= bus_voltage / sqrt(3), iq <= 5.0


def run_case(case: CommissioningCase, controller_params=DEFAULT_CONTROLLER,
             control_dt_s=40e-6):
    """Run both control cases; retain stage, reason, and partial data on failure."""
    required_voltage, voltage_feasible, current_feasible = _voltage_feasibility(
        case.plant, case.dc_bus_voltage_v
    )
    row = {
        "case_id": case.case_id, "seed": case.seed,
        "noise": case.noise.name,
        "current_noise_std_a": case.noise.current_std_a,
        "voltage_noise_std_v": case.noise.voltage_std_v,
        "speed_noise_std_rad_s": case.noise.speed_std_rad_s,
        "commissioning_speed_rpm": case.commissioning_speed_rpm,
        "dc_bus_voltage_v": case.dc_bus_voltage_v,
        "excitation_scale": case.excitation_scale,
        "required_voltage_v": required_voltage,
        "voltage_feasible": voltage_feasible,
        "current_feasible": current_feasible,
        "status": "pending", "failure_stage": "", "failure_reason": "",
        "parameter_accurate": False, "workflow_success": False,
        "quality_accepted": False, "quality_rejection_reasons": "",
        "retuning_applied": False,
    }
    for name in PARAMETERS:
        row[f"true_{name}"] = getattr(case.plant, name)
        row[f"estimate_{name}"] = None
        row[f"error_{name}_percent"] = None
        row[f"standard_error_{name}"] = None
    for stage in ("standstill", "rotating"):
        for metric in ("rank", "condition", "residual_rmse_v_s", "information_fraction",
                       "max_relative_standard_error", "split_difference", "regressor_energy"):
            row[f"{stage}_{metric}"] = None
    for prefix in ("mismatched", "commissioned"):
        for metric in ("speed_rmse_rpm", "iq_tracking_rmse_a",
                       "recovery_time_s", "saturation_fraction"):
            row[f"{prefix}_{metric}"] = None

    def simulate(commissioning_result=None):
        return run_speed_foc_simulation(
            plant_params=case.plant, controller_params=controller_params,
            commissioning_result=commissioning_result,
            dc_bus_voltage=case.dc_bus_voltage_v, dt=control_dt_s,
        )

    try:
        before = _metrics(simulate())
        row.update({f"mismatched_{key}": value for key, value in before.items()})
        if any(not isfinite(value) for key, value in before.items()
               if key != "recovery_time_s"):
            raise ValueError("Mismatched control produced nonfinite metrics")
    except (ValueError, FloatingPointError, OverflowError) as exc:
        row.update(status="control_failed", failure_stage="mismatched_control",
                   failure_reason=str(exc))
        return row

    noise = case.noise
    stage = "standstill_excitation"
    try:
        standstill = simulate_locked_rotor_measurements(
            case.plant,
            ExcitationConfig(
                d_voltage_v=1.2 * case.excitation_scale,
                q_voltage_v=1.4 * case.excitation_scale,
                dc_bus_voltage_v=case.dc_bus_voltage_v,
                current_noise_std_a=noise.current_std_a,
                voltage_noise_std_v=noise.voltage_std_v,
                speed_noise_std_rad_s=noise.speed_std_rad_s,
                seed=case.seed,
            ),
        )
        stage = "rotating_excitation"
        rotating = simulate_driven_rotor_measurements(
            case.plant,
            RotatingExcitationConfig(
                speed_rpm=case.commissioning_speed_rpm,
                q_voltage_base_v=min(6.0, 0.25 * case.dc_bus_voltage_v),
                dc_bus_voltage_v=case.dc_bus_voltage_v,
                current_noise_std_a=noise.current_std_a,
                voltage_noise_std_v=noise.voltage_std_v,
                speed_noise_std_rad_s=noise.speed_std_rad_s,
                seed=case.seed + 1,
            ),
        )
        # The estimator receives measurements and a known pole-pair count only.
        stage = "joint_identification"
        commissioned = commission_from_measurements(
            standstill, rotating, known_pole_pairs=controller_params.pole_pairs
        )
    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        row.update(status="estimator_failed", failure_stage=stage,
                   failure_reason=str(exc))
        return row

    row["quality_accepted"] = commissioned.quality.accepted
    row["quality_rejection_reasons"] = "; ".join(commissioned.quality.rejection_reasons)
    estimates = {}
    for stage, estimate, names in (("standstill", commissioned.electrical, PARAMETERS[:3]),
                                   ("rotating", commissioned.flux, PARAMETERS[3:])):
        if estimate is None:
            continue
        estimates.update({name: getattr(estimate, name) for name in names})
        diag = estimate.diagnostics
        if diag is None:
            continue
        row.update({
            f"{stage}_rank": diag.effective_rank,
            f"{stage}_condition": diag.scaled_condition_number,
            f"{stage}_residual_rmse_v_s": diag.residual_rmse_v_s,
            f"{stage}_information_fraction": diag.noise_information_fraction,
            f"{stage}_split_difference": diag.split_relative_difference,
            f"{stage}_regressor_energy": float(np.min(diag.regressor_energy)),
        })
        if diag.parameter_standard_errors is not None:
            row[f"{stage}_max_relative_standard_error"] = float(np.max(
                diag.parameter_standard_errors / np.abs([estimates[name] for name in names])
            ))
            for name, error in zip(names, diag.parameter_standard_errors):
                row[f"standard_error_{name}"] = float(error)
    for name, value in estimates.items():
        row[f"estimate_{name}"] = value
        row[f"error_{name}_percent"] = 100 * (value / getattr(case.plant, name) - 1)
    row["parameter_accurate"] = all(
        row[f"error_{name}_percent"] is not None and abs(row[f"error_{name}_percent"]) <= 10
        for name in PARAMETERS
    )
    if commissioned.quality.estimator_failure is not None:
        row.update(status="estimator_failed", failure_stage="joint_identification",
                   failure_reason=commissioned.quality.estimator_failure)
        return row
    if not commissioned.quality.accepted:
        row.update(status="quality_rejected", failure_stage="quality_gate",
                   failure_reason=row["quality_rejection_reasons"])
        return row

    row["retuning_applied"] = True
    try:
        after = _metrics(simulate(commissioned))
        row.update({f"commissioned_{key}": value for key, value in after.items()})
        if any(not isfinite(value) for key, value in after.items()
               if key != "recovery_time_s"):
            raise ValueError("Retuned control produced nonfinite metrics")
    except (ValueError, FloatingPointError, OverflowError) as exc:
        row.update(status="control_failed", failure_stage="commissioned_control",
                   failure_reason=str(exc))
        return row

    row["status"] = "completed"
    row["workflow_success"] = bool(
        row["parameter_accurate"]
        and after["speed_rmse_rpm"] <= 10.0
        and after["iq_tracking_rmse_a"] <= 0.05
        and isfinite(after["recovery_time_s"])
        and after["recovery_time_s"] <= 0.1
        and after["speed_rmse_rpm"] <= 1.05 * before["speed_rmse_rpm"]
        and after["iq_tracking_rmse_a"] <= 1.05 * before["iq_tracking_rmse_a"]
    )
    return row


def run_population(config: MonteCarloConfig = MonteCarloConfig(),
                   controller_params=DEFAULT_CONTROLLER):
    return [run_case(case, controller_params, config.control_dt_s)
            for case in generate_cases(config)]


def _statistics(values, population_size):
    finite = np.asarray([v for v in values if v is not None and isfinite(v)], dtype=float)
    return {
        "n_available": int(len(finite)), "n_missing": population_size - int(len(finite)),
        "median": float(np.median(finite)) if len(finite) else None,
        "p95": float(np.percentile(finite, 95)) if len(finite) else None,
        "worst": float(np.max(finite)) if len(finite) else None,
    }


def summarize_population(rows):
    """Report finite-value statistics and missing counts against all cases."""
    if not rows:
        raise ValueError("Population cannot be empty")
    n = len(rows)
    metrics = {}
    for name in PARAMETERS:
        metrics[f"absolute_error_{name}_percent"] = _statistics(
            [abs(row[f"error_{name}_percent"]) if row[f"error_{name}_percent"] is not None
             else None for row in rows], n
        )
    for prefix in ("mismatched", "commissioned"):
        for metric in ("speed_rmse_rpm", "iq_tracking_rmse_a",
                       "recovery_time_s", "saturation_fraction"):
            key = f"{prefix}_{metric}"
            metrics[key] = _statistics([row[key] for row in rows], n)

    paired_metrics = {}
    for metric in ("speed_rmse_rpm", "iq_tracking_rmse_a",
                   "recovery_time_s", "saturation_fraction"):
        paired = [row for row in rows if row["status"] == "completed"
                  and isfinite(row[f"mismatched_{metric}"])
                  and isfinite(row[f"commissioned_{metric}"])]
        before = [row[f"mismatched_{metric}"] for row in paired]
        after = [row[f"commissioned_{metric}"] for row in paired]
        paired_metrics[metric] = {
            "n_pairs": len(paired), "n_unpaired": n - len(paired),
            "mismatched": _statistics(before, len(paired)),
            "commissioned": _statistics(after, len(paired)),
            "improved_count": sum(a < b for a, b in zip(after, before)),
            "worsened_count": sum(a > b for a, b in zip(after, before)),
        }

    condition_rates = {}
    for field in ("noise", "commissioning_speed_rpm", "dc_bus_voltage_v"):
        condition_rates[field] = []
        for value in dict.fromkeys(row[field] for row in rows):
            group = [row for row in rows if row[field] == value]
            condition_rates[field].append({
                "value": value,
                "n": len(group),
                "estimator_failures": sum(row["status"] == "estimator_failed" for row in group),
                "accurate_estimates": sum(row["parameter_accurate"] for row in group),
                "voltage_infeasible": sum(not row["voltage_feasible"] for row in group),
                "successes": sum(row["workflow_success"] for row in group),
                "success_rate": sum(row["workflow_success"] for row in group) / len(group),
            })
    return {
        "total_cases": n,
        "completed_cases": sum(row["status"] == "completed" for row in rows),
        "estimator_failure_count": sum(row["status"] == "estimator_failed" for row in rows),
        "success_count": sum(row["workflow_success"] for row in rows),
        "success_rate": sum(row["workflow_success"] for row in rows) / n,
        "accurate_estimate_count": sum(row["parameter_accurate"] for row in rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "failure_reasons": dict(Counter(
            row["failure_reason"] for row in rows if row["failure_reason"]
        )),
        "voltage_infeasible_count": sum(not row["voltage_feasible"] for row in rows),
        "unrecovered_commissioned_count": sum(
            row["status"] == "completed" and not isfinite(row["commissioned_recovery_time_s"])
            for row in rows
        ),
        "metrics": metrics,
        "paired_metrics": paired_metrics,
        "condition_rates": condition_rates,
        "quality_gate": summarize_quality_gate(rows),
    }


def summarize_quality_gate(rows):
    """Truth is used here only to score the previously recorded gate decision."""
    accepted = [r for r in rows if r["quality_accepted"]]
    rejected = [r for r in rows if r["status"] == "quality_rejected"]
    scorable = [r for r in rows if all(r[f"error_{name}_percent"] is not None
                                      for name in PARAMETERS)]
    false_acceptances = sum(not r["parameter_accurate"] for r in accepted)
    false_rejections = sum(r["parameter_accurate"] for r in rejected)

    def rate(count, denominator):
        return count / denominator if denominator else None

    return {
        "accepted_count": len(accepted),
        "rejected_count_including_failures": len(rows) - len(accepted),
        "quality_rejected_count": len(rejected),
        "estimator_failure_count": sum(r["status"] == "estimator_failed" for r in rows),
        "scorable_estimates": len(scorable),
        "coverage": len(accepted) / len(rows),
        "false_acceptance_count": false_acceptances,
        "false_rejection_count": false_rejections,
        "inaccurate_fraction_of_accepted": rate(false_acceptances, len(accepted)),
        "acceptance_fraction_of_inaccurate_estimates": rate(
            false_acceptances, sum(not r["parameter_accurate"] for r in scorable)),
        "rejection_fraction_of_accurate_estimates": rate(
            false_rejections, sum(r["parameter_accurate"] for r in scorable)),
        "accepted_parameter_reliability": rate(len(accepted) - false_acceptances, len(accepted)),
        "ungated_parameter_reliability": rate(sum(r["parameter_accurate"] for r in scorable), len(scorable)),
        "closed_loop_success_rate_among_accepted": rate(
            sum(r["workflow_success"] for r in accepted), len(accepted)),
        "absolute_error_percent": {
            group: {name: _statistics([abs(r[f"error_{name}_percent"]) for r in subset], len(subset))
                    for name in PARAMETERS}
            for group, subset in (("accepted", accepted), ("quality_rejected", rejected))
        },
    }
