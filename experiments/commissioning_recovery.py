"""Full electrical commissioning and closed-loop controller recovery demo."""

import csv
from pathlib import Path

import matplotlib
import numpy as np

from experiments.parameter_sensitivity import calculate_metrics
from experiments.rotating_flux_identification import save_flux_plot
from src.commissioning import commission_from_measurements
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.motor import PMSMParameters
from src.rotating_identification import (
    RotatingExcitationConfig,
    simulate_driven_rotor_measurements,
)
from src.speed_foc_simulation import run_speed_foc_simulation


DC_BUS_VOLTAGE = 12.0


def _performance_metrics(simulation):
    metrics = calculate_metrics(simulation)
    post_step = simulation["time"] >= simulation["load_step_time"]
    speed_error = simulation["rpm"] - simulation["speed_ref_rpm"]
    current_error = simulation["iq"] - simulation["iq_ref"]
    metrics.update({
        "post_step_speed_rmse_rpm": float(np.sqrt(np.mean(speed_error[post_step] ** 2))),
        "post_step_iq_tracking_rmse_a": float(np.sqrt(np.mean(current_error[post_step] ** 2))),
        "saturation_fraction": float(np.mean(simulation["voltage_saturated"])),
        "final_speed_rpm": float(simulation["rpm"][-1]),
    })
    return metrics


def run_experiment(
    plant_params=None,
    incorrect_controller_params=None,
    standstill_config=None,
    rotating_config=None,
    dc_bus_voltage=DC_BUS_VOLTAGE,
):
    """Commission a hidden plant, retune, and compare three closed-loop runs."""
    plant = plant_params if plant_params is not None else PMSMParameters(
        Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015
    )
    incorrect = incorrect_controller_params if incorrect_controller_params is not None else (
        PMSMParameters(Rs=0.24, Ld=0.6e-3, Lq=1.4e-3, psi_f=0.035)
    )
    standstill_config = standstill_config if standstill_config is not None else ExcitationConfig(
        current_noise_std_a=0.01,
        voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.05,
    )
    rotating_config = rotating_config if rotating_config is not None else RotatingExcitationConfig(
        q_voltage_base_v=5.0,
        current_noise_std_a=0.01,
        voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.05,
    )
    standstill_data = simulate_locked_rotor_measurements(plant, standstill_config)
    rotating_data = simulate_driven_rotor_measurements(plant, rotating_config)
    commissioned = commission_from_measurements(
        standstill_data, rotating_data, known_pole_pairs=incorrect.pole_pairs
    )
    retuned = commissioned.retuned_controller_parameters(incorrect)

    cases = (
        ("true-parameter reference", plant, None),
        ("mismatched", incorrect, None),
        ("self-commissioned", incorrect, commissioned),
    )
    simulations = {}
    performance = []
    for name, assumed, commissioning_result in cases:
        simulation = run_speed_foc_simulation(
            plant_params=plant,
            controller_params=assumed,
            dc_bus_voltage=dc_bus_voltage,
            commissioning_result=commissioning_result,
        )
        simulations[name] = simulation
        performance.append({"controller": name, **_performance_metrics(simulation)})

    parameter_rows = [
        {
            "parameter": name,
            "unit": unit,
            "true_value": getattr(plant, name),
            "initial_controller_value": getattr(incorrect, name),
            "estimated_value": getattr(retuned, name),
            "estimation_error_percent": 100 * (getattr(retuned, name) / getattr(plant, name) - 1),
        }
        for name, unit in (("Rs", "ohm"), ("Ld", "H"), ("Lq", "H"), ("psi_f", "Wb"))
    ]
    return {
        "commissioning": commissioned,
        "rotating_data": rotating_data,
        "simulations": simulations,
        "performance": performance,
        "parameter_rows": parameter_rows,
        "retuned_controller_params": retuned,
    }


def save_results(result, output_dir=Path("results")):
    """Save parameter and performance tables plus identification/recovery plots."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parameter_path = output_dir / "commissioning_parameter_estimates.csv"
    performance_path = output_dir / "commissioning_performance.csv"
    for path, rows in ((parameter_path, result["parameter_rows"]),
                       (performance_path, result["performance"])):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    identification_plot = output_dir / "commissioning_flux_identification.png"
    true_flux = next(row["true_value"] for row in result["parameter_rows"]
                     if row["parameter"] == "psi_f")
    save_flux_plot(result["rotating_data"], result["commissioning"].flux,
                   true_flux, identification_plot)

    simulations = result["simulations"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    colors = {"true-parameter reference": "black", "mismatched": "tab:red",
              "self-commissioned": "tab:green"}
    for name, sim in simulations.items():
        time = sim["time"]
        color = colors[name]
        axes[0, 0].plot(time, sim["rpm"], color=color, label=name)
        post = (time >= sim["load_step_time"] - 0.01) & (time <= sim["load_step_time"] + 0.12)
        axes[0, 1].plot(time[post], sim["rpm"][post] - sim["speed_ref_rpm"],
                        color=color, label=name)
        axes[1, 0].plot(time[post], (sim["iq"] - sim["iq_ref"])[post],
                        color=color, label=name)
        axes[1, 1].plot(time, sim["voltage_magnitude"], color=color, label=name)
    axes[0, 0].axhline(1000, color="gray", linestyle=":")
    axes[0, 0].set_ylabel("Speed [rpm]")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].axhline(0, color="gray", linestyle=":")
    axes[0, 1].set_ylabel("Post-load speed error [rpm]")
    axes[1, 0].axhline(0, color="gray", linestyle=":")
    axes[1, 0].set_ylabel("Post-load iq tracking error [A]")
    axes[1, 1].axhline(next(iter(simulations.values()))["voltage_limit"],
                       color="gray", linestyle="--", label="SVPWM limit")
    axes[1, 1].set_ylabel("Applied voltage magnitude [V]")
    axes[1, 1].legend(fontsize=8)
    for ax in axes.flat:
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=0.3)
    fig.suptitle("Controller performance before and after self-commissioning")
    fig.tight_layout()
    recovery_plot = output_dir / "commissioning_performance.png"
    fig.savefig(recovery_plot, dpi=180)
    plt.close(fig)
    return parameter_path, performance_path, identification_plot, recovery_plot


def main():
    result = run_experiment()
    for row in result["parameter_rows"]:
        print(f'{row["parameter"]}: {row["estimated_value"]:.8g} '
              f'({row["estimation_error_percent"]:+.3f}% error)')
    for row in result["performance"]:
        print(f'{row["controller"]}: post-load speed RMSE '
              f'{row["post_step_speed_rmse_rpm"]:.2f} rpm, '
              f'iq RMSE {row["post_step_iq_tracking_rmse_a"]:.4f} A')
    for path in save_results(result):
        print(path)


if __name__ == "__main__":
    main()
