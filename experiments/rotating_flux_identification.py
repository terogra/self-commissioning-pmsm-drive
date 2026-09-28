"""Independent driven-rotor flux-linkage identification experiment."""

import csv
from pathlib import Path

import matplotlib
import numpy as np

from src.identification import (
    ExcitationConfig,
    estimate_standstill_parameters,
    simulate_locked_rotor_measurements,
)
from src.motor import PMSMParameters
from src.rotating_identification import (
    RotatingExcitationConfig,
    estimate_flux_linkage,
    simulate_driven_rotor_measurements,
)


def run_experiment(plant_params=None, standstill_config=None, rotating_config=None):
    """Identify electrical constants in two distinct sampled-data tests."""
    plant = plant_params if plant_params is not None else PMSMParameters(
        Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015
    )
    standstill_config = standstill_config if standstill_config is not None else ExcitationConfig(
        current_noise_std_a=0.01, voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.05,
    )
    rotating_config = rotating_config if rotating_config is not None else RotatingExcitationConfig(
        q_voltage_base_v=5.0, current_noise_std_a=0.01,
        voltage_noise_std_v=0.01, speed_noise_std_rad_s=0.05,
    )
    standstill_data = simulate_locked_rotor_measurements(plant, standstill_config)
    electrical = estimate_standstill_parameters(standstill_data)
    rotating_data = simulate_driven_rotor_measurements(plant, rotating_config)
    flux = estimate_flux_linkage(rotating_data, electrical, pole_pairs=plant.pole_pairs)
    return {"electrical": electrical, "rotating_data": rotating_data,
            "flux": flux, "true_psi_f": plant.psi_f}


def save_flux_plot(data, flux, true_psi_f, path):
    """Plot sampled signals, q-axis regression fit, and estimate convergence."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].plot(data.time_s, data.speed_rad_s * 60 / (2 * np.pi))
    axes[0, 0].set_ylabel("Driven rotor speed [rpm]")
    axes[0, 1].plot(data.time_s, data.current_q_a, label="measured iq [A]")
    axes[0, 1].plot(data.time_s[:-1], data.voltage_q_v, alpha=0.65,
                    label="measured vq [V]")
    axes[0, 1].set_ylabel("iq [A] / vq [V]")
    axes[0, 1].legend()
    axes[1, 0].plot(flux.window_time_s, flux.observed_back_emf_integral_v_s,
                    label="observed integrated back-EMF")
    axes[1, 0].plot(flux.window_time_s, flux.fitted_back_emf_integral_v_s,
                    linestyle="--", label="fitted")
    axes[1, 0].set_ylabel("Window voltage integral [V s]")
    axes[1, 0].legend()
    axes[1, 1].plot(flux.convergence_time_s, flux.convergence_psi_f * 1e3,
                    label="estimated psi_f")
    axes[1, 1].axhline(true_psi_f * 1e3, color="black", linestyle="--",
                       label="hidden plant value")
    axes[1, 1].set_ylabel("Flux linkage [mWb]")
    axes[1, 1].legend()
    for ax in axes.flat:
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=0.3)
    fig.suptitle("Rotating flux-linkage identification")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_results(result, output_dir=Path("results")):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    table = output_dir / "rotating_flux_identification.csv"
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "true_psi_f_wb", "estimated_psi_f_wb", "error_percent", "regression_rmse_v_s"
        ))
        writer.writeheader()
        writer.writerow({
            "true_psi_f_wb": result["true_psi_f"],
            "estimated_psi_f_wb": result["flux"].psi_f,
            "error_percent": 100 * (result["flux"].psi_f / result["true_psi_f"] - 1),
            "regression_rmse_v_s": result["flux"].regression_rmse_v_s,
        })
    figure = output_dir / "rotating_flux_identification.png"
    save_flux_plot(result["rotating_data"], result["flux"], result["true_psi_f"], figure)
    return table, figure


def main():
    result = run_experiment()
    print(f'psi_f: {result["flux"].psi_f:.8g} Wb '
          f'({100 * (result["flux"].psi_f / result["true_psi_f"] - 1):+.3f}% error)')
    for path in save_results(result):
        print(path)


if __name__ == "__main__":
    main()
