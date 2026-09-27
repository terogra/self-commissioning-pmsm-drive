"""One-at-a-time plant/controller parameter mismatch experiments."""

import csv
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np

from src.motor import PMSMParameters
from src.speed_foc_simulation import run_speed_foc_simulation


PARAMETERS = ("Rs", "Ld", "Lq", "psi_f")
MISMATCH_PERCENTS = (-40, -20, 20, 40)


def calculate_metrics(simulation, recovery_band_rpm=None):
    """Measure tracking and load response for a single simulation.

    RMSEs cover the entire run, including startup. Recovery is the first time
    after the load step that speed enters and then stays within the band around
    the speed reference. NaN means it did not recover before the run ended.
    """
    time = simulation["time"]
    rpm = simulation["rpm"]
    speed_ref = simulation["speed_ref_rpm"]
    iq_error = simulation["iq"] - simulation["iq_ref"]
    load_step_time = simulation["load_step_time"]
    band = 0.01 * abs(speed_ref) if recovery_band_rpm is None else recovery_band_rpm
    if band <= 0:
        raise ValueError("Recovery band must be positive")

    post_step = time >= load_step_time
    if not np.any(post_step):
        raise ValueError("Simulation must include samples after the load step")

    post_time = time[post_step]
    post_error = np.abs(rpm[post_step] - speed_ref)
    outside = np.flatnonzero(post_error > band)
    if outside.size == 0:
        recovery_time = 0.0
    elif outside[-1] == len(post_time) - 1:
        recovery_time = float("nan")
    else:
        recovery_time = float(post_time[outside[-1] + 1] - load_step_time)

    return {
        "speed_rmse_rpm": float(np.sqrt(np.mean((rpm - speed_ref) ** 2))),
        "iq_tracking_rmse_a": float(np.sqrt(np.mean(iq_error ** 2))),
        "max_post_step_speed_deviation_rpm": float(np.max(post_error)),
        "disturbance_recovery_time_s": recovery_time,
    }


def run_sweep(nominal_params=None, **simulation_options):
    """Hold controller assumptions nominal and vary one plant field per run."""
    nominal_params = nominal_params if nominal_params is not None else PMSMParameters()
    cases = [("nominal", 0, nominal_params)]
    for parameter in PARAMETERS:
        for mismatch_pct in MISMATCH_PERCENTS:
            plant_params = replace(
                nominal_params,
                **{parameter: getattr(nominal_params, parameter) * (1 + mismatch_pct / 100)},
            )
            cases.append((parameter, mismatch_pct, plant_params))

    results = []
    for parameter, mismatch_pct, plant_params in cases:
        simulation = run_speed_foc_simulation(
            plant_params=plant_params,
            controller_params=replace(nominal_params),
            **simulation_options,
        )
        metrics = calculate_metrics(simulation)
        results.append({
            "parameter": parameter,
            "mismatch_pct": mismatch_pct,
            "plant_value": getattr(plant_params, parameter) if parameter != "nominal" else "",
            "controller_value": getattr(nominal_params, parameter) if parameter != "nominal" else "",
            **metrics,
            "simulation": simulation,
        })
    return results


def save_results(results, output_dir=Path("results")):
    """Write a metric table and comparison figures, returning their paths."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "parameter_mismatch_metrics.csv"
    columns = [key for key in results[0] if key != "simulation"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row[key] for key in columns} for row in results)

    nominal = results[0]["simulation"]
    window = (
        (nominal["time"] >= nominal["load_step_time"] - 0.01)
        & (nominal["time"] <= nominal["load_step_time"] + 0.10)
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
    for ax, parameter in zip(axes.flat, PARAMETERS):
        ax.plot(
            nominal["time"][window],
            nominal["rpm"][window] - nominal["speed_ref_rpm"],
            color="black", label="nominal",
        )
        for row in results[1:]:
            if row["parameter"] == parameter:
                sim = row["simulation"]
                ax.plot(
                    sim["time"][window],
                    sim["rpm"][window] - sim["speed_ref_rpm"],
                    label=f'{row["mismatch_pct"]:+d}%',
                )
        ax.axhline(0, color="gray", linestyle="--", linewidth=1)
        ax.axvline(nominal["load_step_time"], color="gray", linestyle=":", linewidth=1)
        ax.set_title(parameter)
        ax.set_ylabel("Speed error [rpm]")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("Time [s]")
    fig.suptitle("Load-step speed response: plant mismatch, nominal controller")
    fig.tight_layout()
    speed_path = output_dir / "parameter_mismatch_speed.png"
    fig.savefig(speed_path, dpi=180)
    plt.close(fig)

    metric_labels = (
        ("speed_rmse_rpm", "Speed RMSE [rpm]"),
        ("iq_tracking_rmse_a", "iq tracking RMSE [A]"),
        ("max_post_step_speed_deviation_rpm", "Max speed deviation [rpm]"),
        ("disturbance_recovery_time_s", "Recovery time [s]"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for ax, (key, label) in zip(axes.flat, metric_labels):
        for parameter in PARAMETERS:
            rows = [row for row in results if row["parameter"] == parameter]
            ax.plot(
                [row["mismatch_pct"] for row in rows],
                [row[key] for row in rows],
                marker="o",
                label=parameter,
            )
        ax.axhline(results[0][key], color="black", linestyle="--", label="nominal")
        ax.set_xlabel("Plant mismatch [%]")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("Parameter mismatch sensitivity metrics")
    fig.tight_layout()
    metrics_path = output_dir / "parameter_mismatch_metrics.png"
    fig.savefig(metrics_path, dpi=180)
    plt.close(fig)
    return csv_path, speed_path, metrics_path


def main():
    results = run_sweep()
    paths = save_results(results)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
