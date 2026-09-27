"""Reproducible locked-rotor Rs/Ld/Lq commissioning experiment."""

import csv
from pathlib import Path

import matplotlib
import numpy as np

from src.identification import (
    ExcitationConfig,
    estimate_standstill_parameters,
    predict_standstill_currents,
    simulate_locked_rotor_measurements,
)
from src.motor import PMSMParameters


def run_experiment(
    plant_params=None,
    config=None,
):
    """Estimate only from measurements, then reveal plant values for scoring."""
    plant_params = plant_params if plant_params is not None else PMSMParameters(
        Rs=0.48, Ld=0.8e-3, Lq=1.25e-3
    )
    config = config if config is not None else ExcitationConfig(
        current_noise_std_a=0.01,
        voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.05,
    )
    measurements = simulate_locked_rotor_measurements(plant_params, config)
    estimate = estimate_standstill_parameters(measurements)
    predicted_d, predicted_q = predict_standstill_currents(measurements, estimate)
    comparison = [
        {
            "parameter": name,
            "unit": unit,
            "true_value": getattr(plant_params, name),
            "estimated_value": getattr(estimate, name),
            "error_percent": 100 * (getattr(estimate, name) / getattr(plant_params, name) - 1),
        }
        for name, unit in (("Rs", "ohm"), ("Ld", "H"), ("Lq", "H"))
    ]
    return measurements, estimate, predicted_d, predicted_q, comparison


def save_results(result, output_dir=Path("results")):
    """Save an error table and diagnostic figure for the commissioning run."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data, estimate, predicted_d, predicted_q, comparison = result
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "standstill_identification.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=comparison[0].keys())
        writer.writeheader()
        writer.writerows(comparison)

    time = data.time_s
    preview = time <= 0.10
    fig, axes = plt.subplots(3, 2, figsize=(12, 11))
    axes[0, 0].step(time[:-1][preview[:-1]], data.voltage_d_v[preview[:-1]],
                    where="post", label="measured vd")
    axes[0, 0].step(time[:-1][preview[:-1]], data.voltage_q_v[preview[:-1]],
                    where="post", label="measured vq")
    axes[0, 0].set_ylabel("dq voltage [V]")
    axes[0, 0].legend()
    axes[0, 1].plot(time, data.speed_rad_s)
    axes[0, 1].set_ylabel("Measured rotor speed [rad/s]")

    axes[1, 0].plot(time[preview], data.current_d_a[preview], alpha=0.65,
                    label="measured id")
    axes[1, 0].plot(time[preview], predicted_d[preview], linestyle="--",
                    label="fitted id")
    axes[1, 0].set_ylabel("d-axis current [A]")
    axes[1, 0].legend()
    axes[1, 1].plot(time[preview], data.current_q_a[preview], alpha=0.65,
                    label="measured iq")
    axes[1, 1].plot(time[preview], predicted_q[preview], linestyle="--",
                    label="fitted iq")
    axes[1, 1].set_ylabel("q-axis current [A]")
    axes[1, 1].legend()

    for index, row in enumerate(comparison):
        error = 100 * (
            estimate.convergence_parameters[:, index] / row["true_value"] - 1
        )
        axes[2, 0].plot(estimate.convergence_time_s, error,
                        label=row["parameter"])
    axes[2, 0].axhline(0, color="black", linestyle=":")
    axes[2, 0].set_ylabel("Parameter error [%]")
    axes[2, 0].legend()
    axes[2, 1].plot(time, data.current_d_a - predicted_d, label="id residual")
    axes[2, 1].plot(time, data.current_q_a - predicted_q, label="iq residual")
    axes[2, 1].set_ylabel("Measured − fitted current [A]")
    axes[2, 1].legend()
    for ax in axes.flat:
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=0.3)
    fig.suptitle("Locked-rotor Rs/Ld/Lq identification from sampled measurements")
    fig.tight_layout()
    plot_path = output_dir / "standstill_identification.png"
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)
    return csv_path, plot_path


def main():
    result = run_experiment()
    for row in result[-1]:
        print(
            f'{row["parameter"]}: {row["estimated_value"]:.8g} {row["unit"]} '
            f'(true {row["true_value"]:.8g}, error {row["error_percent"]:+.3f}%)'
        )
    for path in save_results(result):
        print(path)


if __name__ == "__main__":
    main()
