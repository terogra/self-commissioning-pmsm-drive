"""Small reproducible extension of the existing population design to J and B.

Thresholds are fixed engineering budgets, not fitted to truth labels. Every
case, failed stage, and fallback control run is retained.
"""

import argparse
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path

import matplotlib
import numpy as np

from experiments.full_commissioning_recovery import run_experiment
from src.mechanical_excitation import MechanicalExcitationConfig
from src.mechanical_identification import MechanicalQualityPolicy
from src.monte_carlo import MonteCarloConfig, NoiseCondition, _statistics, generate_cases


SEEDS = {"development": 20261011, "evaluation": 20261012}


def population_config(population):
    noise = (NoiseCondition("low", 0.01, 0, 0.05), NoiseCondition("high", 0.2, 0, 1.0))
    if population == "evaluation":
        noise = (noise[0], NoiseCondition("medium", 0.04, 0, 0.2), noise[1])
    return MonteCarloConfig(seed=SEEDS[population], repeats=1, noise_conditions=noise,
                            commissioning_speeds_rpm=(600.0,),
                            dc_bus_voltages_v=(24.0,) if population == "development" else (12.0, 24.0),
                            excitation_scales=(0.08, 1.0))


def generate_mechanical_cases(population):
    config = population_config(population)
    # Independent stream for mechanics; existing electrical generator unchanged.
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, 1]))
    return [replace(case, plant=replace(case.plant, J=float(rng.uniform(1.5e-4, 9e-4)),
                                       B=float(rng.uniform(0.5e-4, 5e-4))))
            for case in generate_cases(config)]


def run_population(population):
    rows = []
    for case in generate_mechanical_cases(population):
        row = {"case_id": case.case_id, "seed": case.seed, "noise": case.noise.name,
               "electrical_seed": case.seed+1, "current_noise_std_a": case.noise.current_std_a,
               "speed_noise_std_rad_s": case.noise.speed_std_rad_s,
               "excitation_scale": case.excitation_scale, "dc_bus_voltage_v": case.dc_bus_voltage_v,
               **{f"true_{k}": getattr(case.plant, k) for k in ("Rs", "Ld", "Lq", "psi_f", "J", "B")},
               "electrical_accepted": False, "mechanical_accepted": False, "full_accepted": False,
               "status": "pending", "reason": "", "parameter_accurate": False, "control_success": False,
               "estimate_J": None, "estimate_B": None, "error_J_percent": None, "error_B_percent": None,
               "condition": None, "information_fraction": None, "relative_sensitivity": None,
               "minimum_component_snr": None}
        for name in ("mismatched", "electrical-only", "full commissioned", "oracle"):
            for metric in ("post_step_speed_rmse_rpm", "post_step_iq_tracking_rmse_a",
                           "disturbance_recovery_time_s", "saturation_fraction"):
                row[f"{name}_{metric}"] = None
        config = MechanicalExcitationConfig(
            iq_plateaus_a=tuple(case.excitation_scale*v for v in MechanicalExcitationConfig().iq_plateaus_a),
            current_noise_std_a=case.noise.current_std_a, speed_noise_std_rad_s=case.noise.speed_std_rad_s,
            dc_bus_voltage_v=case.dc_bus_voltage_v, seed=case.seed,
        )
        try:
            result = run_experiment(plant=case.plant, mechanical_config=config,
                                    dc_bus_voltage=case.dc_bus_voltage_v, electrical_seed=case.seed+1)
            full = result["full"]
            row.update(electrical_accepted=full.electrical.quality.accepted,
                       mechanical_accepted=full.mechanical.quality.accepted, full_accepted=full.quality.accepted,
                       reason="; ".join(full.quality.rejection_reasons))
            row["status"] = ("electrical_rejected" if not full.electrical.quality.accepted else
                             "estimator_failed" if full.mechanical.quality.estimator_failure else
                             "accepted" if full.quality.accepted else "quality_rejected")
            estimate = full.mechanical.estimate
            if estimate is not None:
                for name in ("J", "B"):
                    row[f"estimate_{name}"] = getattr(estimate, name)
                    row[f"error_{name}_percent"] = 100*abs(getattr(estimate, name)/getattr(case.plant, name)-1)
                row["parameter_accurate"] = max(row["error_J_percent"], row["error_B_percent"]) <= 10
                d = estimate.diagnostics
                row.update(condition=d.scaled_condition_number, information_fraction=d.noise_information_fraction,
                           relative_sensitivity=None if d.standard_error_bound is None else
                           float(np.max(d.standard_error_bound/np.array([estimate.J, estimate.B]))),
                           minimum_component_snr=None if d.component_snr is None else float(np.min(d.component_snr)))
            for performance in result["performance"]:
                for metric in ("post_step_speed_rmse_rpm", "post_step_iq_tracking_rmse_a",
                               "disturbance_recovery_time_s", "saturation_fraction"):
                    value = performance[metric]
                    row[f'{performance["controller"]}_{metric}'] = float(value) if np.isfinite(value) else None
            row["control_success"] = bool(full.quality.accepted and row["parameter_accurate"]
                and row["full commissioned_post_step_speed_rmse_rpm"] <= 10
                and row["full commissioned_post_step_iq_tracking_rmse_a"] <= 0.05
                and row["full commissioned_disturbance_recovery_time_s"] is not None
                and row["full commissioned_disturbance_recovery_time_s"] <= 0.10)
        except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            row.update(status="simulation_failed", reason=str(exc))
        rows.append(row)
    return rows


def summarize(rows):
    accepted = [r for r in rows if r["full_accepted"]]
    scorable = [r for r in rows if r["estimate_J"] is not None and r["estimate_B"] is not None]
    inaccurate = [r for r in scorable if not r["parameter_accurate"]]
    accurate = [r for r in scorable if r["parameter_accurate"]]
    def fraction(n, d):
        return n/d if d else None
    fa = sum(not r["parameter_accurate"] for r in accepted)
    fr = sum(not r["full_accepted"] for r in accurate)
    return {"total_cases": len(rows), "status_counts": {status: sum(r["status"] == status for r in rows)
            for status in sorted({r["status"] for r in rows})},
            "accepted_count": len(accepted), "coverage": fraction(len(accepted), len(rows)),
            "false_acceptance_count": fa, "inaccurate_fraction_of_accepted": fraction(fa, len(accepted)),
            "acceptance_fraction_of_inaccurate": fraction(fa, len(inaccurate)),
            "false_rejection_count": fr, "rejection_fraction_of_accurate": fraction(fr, len(accurate)),
            "accepted_control_successes": sum(r["control_success"] for r in accepted),
            "accepted_control_success_rate": fraction(sum(r["control_success"] for r in accepted), len(accepted)),
            "parameter_errors": {label: {k: _statistics([r[f"error_{k}_percent"] for r in group], len(group))
                for k in ("J", "B")} for label, group in (("all", rows), ("accepted", accepted),
                    ("rejected_with_estimates", [r for r in scorable if not r["full_accepted"]]))},
            "accepted_performance": {name: {metric: _statistics([r[f"{name}_{metric}"] for r in accepted], len(accepted))
                for metric in ("post_step_speed_rmse_rpm", "post_step_iq_tracking_rmse_a",
                               "disturbance_recovery_time_s", "saturation_fraction")}
                for name in ("mismatched", "electrical-only", "full commissioned", "oracle")}}


def save_results(rows, population, output_dir=None):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output_dir = Path(output_dir or f"results/mechanical_population/{population}")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    summary["methodology"] = {"config": asdict(population_config(population)),
                              "mechanical_policy": asdict(MechanicalQualityPolicy()),
                              "J_range": [1.5e-4, 9e-4], "B_range": [0.5e-4, 5e-4],
                              "electrical_sensor_noise": [0.01, 0.01, 0.02],
                              "thresholds": "Pre-specified engineering budgets; no truth-label fitting"}
    with (output_dir / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    plot_results(rows, population, output_dir / "population.png")
    return summary


def plot_results(rows, population, path):
    """Render saved outcomes without rerunning experiments or changing decisions."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for accepted, label, color in ((True, "accepted", "tab:green"), (False, "rejected", "tab:orange")):
        subset = [r for r in rows if r["full_accepted"] == accepted and r["estimate_J"] is not None]
        axes[0].scatter([r["error_J_percent"] for r in subset], [r["error_B_percent"] for r in subset], label=label, color=color)
    axes[0].set(xlabel="J absolute error [%]", ylabel="B absolute error [%]", xscale="symlog", yscale="symlog")
    axes[0].legend()
    accepted = [r for r in rows if r["full_accepted"]]
    for name in ("electrical-only", "oracle"):
        axes[1].scatter([r[f"{name}_post_step_speed_rmse_rpm"] for r in accepted],
                        [r["full commissioned_post_step_speed_rmse_rpm"] for r in accepted],
                        label=name, marker="x" if name == "oracle" else "o")
    upper = max([r["full commissioned_post_step_speed_rmse_rpm"] for r in accepted] + [1])*1.1
    axes[1].plot([0, upper], [0, upper], "k:", linewidth=1)
    axes[1].set(xlabel="Reference speed RMSE [rpm]", ylabel="Full commissioned speed RMSE [rpm]",
                xscale="symlog", yscale="symlog")
    axes[1].legend()
    for noise in dict.fromkeys(r["noise"] for r in rows):
        subset = [r for r in rows if r["noise"] == noise]
        axes[2].bar(noise, sum(r["full_accepted"] for r in subset)/len(subset))
    axes[2].set(ylabel="Acceptance fraction (all cases)", ylim=(0, 1))
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.suptitle(f"{population}: n={len(rows)}, accepted={len(accepted)}; all failures retained in CSV")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", choices=SEEDS, required=True)
    population = parser.parse_args().population
    summary = save_results(run_population(population), population)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("accepted_performance", "parameter_errors", "methodology")}, indent=2))
