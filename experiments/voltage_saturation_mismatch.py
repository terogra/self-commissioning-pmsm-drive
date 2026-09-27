"""Compare flux-linkage mismatch with a limited and ideal voltage source."""

import csv
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np

from experiments.parameter_sensitivity import calculate_metrics
from src.motor import PMSMParameters
from src.speed_foc_simulation import run_speed_foc_simulation


MISMATCH_PERCENTS = (-40, 0, 40)
EXPERIMENT_DC_BUS_VOLTAGE = 24.0


def run_experiment(nominal_params=None, dc_bus_voltage=EXPERIMENT_DC_BUS_VOLTAGE):
    """Vary physical psi_f while keeping controller assumptions nominal."""
    nominal_params = nominal_params if nominal_params is not None else PMSMParameters()
    if dc_bus_voltage <= 0 or not np.isfinite(dc_bus_voltage):
        raise ValueError("dc_bus_voltage must be positive and finite")

    results = []
    for mismatch_pct in MISMATCH_PERCENTS:
        plant_params = replace(
            nominal_params,
            psi_f=nominal_params.psi_f * (1 + mismatch_pct / 100),
        )
        for voltage_mode, bus_voltage in (
            ("limited", dc_bus_voltage),
            ("unconstrained", None),
        ):
            simulation = run_speed_foc_simulation(
                plant_params=plant_params,
                controller_params=replace(nominal_params),
                dc_bus_voltage=bus_voltage,
            )
            results.append({
                "psi_f_mismatch_pct": mismatch_pct,
                "plant_psi_f_wb": plant_params.psi_f,
                "controller_psi_f_wb": nominal_params.psi_f,
                "voltage_mode": voltage_mode,
                "dc_bus_voltage_v": bus_voltage if bus_voltage is not None else "",
                "voltage_limit_v": simulation["voltage_limit"] if bus_voltage is not None else "",
                "saturation_fraction": float(np.mean(simulation["voltage_saturated"])),
                "final_speed_rpm": float(simulation["rpm"][-1]),
                "max_requested_voltage_v": float(np.max(simulation["requested_voltage_magnitude"])),
                **calculate_metrics(simulation),
                "simulation": simulation,
            })
    return results


def save_results(results, output_dir=Path("results")):
    """Save the case table and a comparison plot."""
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "voltage_saturation_mismatch.csv"
    columns = [key for key in results[0] if key != "simulation"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row[key] for key in columns} for row in results)

    fig, axes = plt.subplots(3, 1, figsize=(10, 11), sharex=True)
    colors = {-40: "tab:blue", 0: "tab:green", 40: "tab:red"}
    for row in results:
        sim = row["simulation"]
        mismatch_pct = row["psi_f_mismatch_pct"]
        linestyle = "-" if row["voltage_mode"] == "limited" else "--"
        label = f'{mismatch_pct:+d}% psi_f, {row["voltage_mode"]}'
        axes[0].plot(sim["time"], sim["rpm"], color=colors[mismatch_pct],
                     linestyle=linestyle, label=label)
    axes[0].axhline(results[0]["simulation"]["speed_ref_rpm"],
                    color="black", linestyle=":", label="speed reference")
    axes[0].set_ylabel("Speed [rpm]")
    axes[0].legend(fontsize=8, ncol=2)

    selected = [row for row in results if row["psi_f_mismatch_pct"] == 40]
    for row in selected:
        sim = row["simulation"]
        axes[1].plot(sim["time"], sim["voltage_magnitude"],
                     linestyle="-" if row["voltage_mode"] == "limited" else "--",
                     label=row["voltage_mode"])
        axes[2].plot(sim["time"], sim["iq"],
                     linestyle="-" if row["voltage_mode"] == "limited" else "--",
                     label=f'iq, {row["voltage_mode"]}')
    limited = selected[0]["simulation"]
    axes[1].axhline(limited["voltage_limit"], color="black", linestyle=":",
                    label="24 V bus SVPWM limit")
    axes[1].set_ylabel("Applied dq voltage magnitude [V]")
    axes[1].legend()
    axes[2].plot(limited["time"], limited["iq_ref"], color="black",
                 linestyle=":", label="iq reference, limited")
    axes[2].set_ylabel("q-axis current [A]")
    axes[2].set_xlabel("Time [s]")
    axes[2].legend()
    for ax in axes:
        ax.axvline(limited["load_step_time"], color="gray", linestyle=":")
        ax.grid(alpha=0.3)
    fig.suptitle("Flux mismatch with and without DC-bus voltage saturation")
    fig.tight_layout()
    plot_path = output_dir / "voltage_saturation_mismatch.png"
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)
    return csv_path, plot_path


def main():
    results = run_experiment()
    for path in save_results(results):
        print(path)


if __name__ == "__main__":
    main()
