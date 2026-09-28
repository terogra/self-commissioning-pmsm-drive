"""Four-controller comparison isolating the contribution of measured J/B."""

import csv
from dataclasses import asdict
import json
from pathlib import Path

import matplotlib
import numpy as np

from experiments.commissioning_recovery import _performance_metrics
from src.commissioning import commission_from_measurements
from src.full_commissioning import complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.mechanical_identification import MechanicalQualityPolicy, reconstruct_torque
from src.motor import PMSMParameters
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation


def run_experiment(plant=None, prior=None, mechanical_config=None, dc_bus_voltage=24.0, electrical_seed=101):
    # Existing electrical mismatch, now with 2.5x inertia and 3x viscous friction.
    plant = plant if plant is not None else PMSMParameters(
        Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015, J=5e-4, B=3e-4,
    )
    prior = prior if prior is not None else PMSMParameters(
        Rs=0.24, Ld=0.6e-3, Lq=1.4e-3, psi_f=0.035, J=2e-4, B=1e-4,
    )
    config = mechanical_config if mechanical_config is not None else MechanicalExcitationConfig()
    locked = simulate_locked_rotor_measurements(plant, ExcitationConfig(
        current_noise_std_a=0.01, voltage_noise_std_v=0.01, speed_noise_std_rad_s=0.02, seed=electrical_seed,
    ))
    rotating = simulate_driven_rotor_measurements(plant, RotatingExcitationConfig(
        q_voltage_base_v=5.0, current_noise_std_a=0.01, voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.02, seed=electrical_seed+1,
    ))
    electrical = commission_from_measurements(locked, rotating, prior.pole_pairs)
    # Only electrical estimates and prior assumptions enter the excitation FOC.
    record = None
    if electrical.quality.accepted:
        record = simulate_mechanical_measurements(plant, electrical.retuned_controller_parameters(prior), config)
    full = complete_commissioning(electrical, None if record is None else record.measurements)
    cases = (("oracle", plant, None), ("mismatched", prior, None),
             ("electrical-only", prior, electrical), ("full commissioned", prior, full))
    simulations, performance = {}, []
    for name, assumed, result in cases:
        sim = run_speed_foc_simulation(plant_params=plant, controller_params=assumed,
                                      commissioning_result=result, dc_bus_voltage=dc_bus_voltage)
        metrics = _performance_metrics(sim)
        startup = sim["time"] < sim["load_step_time"]
        metrics["startup_overshoot_rpm"] = float(max(0, np.max(sim["rpm"][startup] - sim["speed_ref_rpm"])))
        performance.append({"controller": name, "commissioning_accepted": sim["commissioning_accepted"], **metrics})
        simulations[name] = sim
    parameter_rows = []
    for names, estimate in ((("Rs", "Ld", "Lq"), electrical.electrical),
                            (("psi_f",), electrical.flux), (("J", "B"), full.mechanical.estimate)):
        for name in names:
            value = None if estimate is None else getattr(estimate, name)
            parameter_rows.append({"parameter": name, "true_value": getattr(plant, name),
                                   "prior_value": getattr(prior, name), "estimate": value,
                                   "absolute_error_percent": None if value is None else
                                   100 * abs(value / getattr(plant, name) - 1)})
    return dict(full=full, record=record, config=config, simulations=simulations,
                performance=performance, parameter_rows=parameter_rows)


def _json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    raise TypeError(type(value).__name__)


def save_results(result, output_dir=Path("results/mechanical_commissioning")):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("parameters", result["parameter_rows"]), ("performance", result["performance"])):
        with (output_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    full = result["full"]
    estimate = full.mechanical.estimate
    summary = {"excitation": asdict(result["config"]), "policy": asdict(MechanicalQualityPolicy()),
               "electrical_quality": asdict(full.electrical.quality),
               "mechanical_quality": asdict(full.mechanical.quality), "overall_quality": asdict(full.quality),
               "diagnostics": None if estimate is None else asdict(estimate.diagnostics),
               "mechanical_excitation_saturation_fraction": None if result["record"] is None else result["record"].saturation_fraction}
    (output_dir / "diagnostics.json").write_text(json.dumps(summary, default=_json_value, indent=2, allow_nan=False), encoding="utf-8")
    if estimate is not None:
        data = result["record"].measurements
        torque = reconstruct_torque(data, full.electrical.electrical, full.electrical.flux, full.electrical.pole_pairs)
        np.savetxt(output_dir / "measurements.csv", np.column_stack((data.time_s, data.current_d_a,
                   data.current_q_a, data.speed_rad_s, torque, result["record"].iq_reference_a,
                   result["record"].applied_voltage_magnitude_v)), delimiter=",", comments="",
                   header="time_s,id_a,iq_a,speed_rad_s,reconstructed_torque_nm,iq_reference_a,voltage_magnitude_v")
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        axes[0, 0].plot(data.time_s, data.speed_rad_s)
        axes[0, 0].set_ylabel("Measured speed [rad/s]")
        axes[0, 1].plot(data.time_s, data.current_q_a, label="measured iq")
        axes[0, 1].plot(data.time_s, result["record"].iq_reference_a, "--", label="iq reference")
        axes[0, 1].set_ylabel("Current [A]")
        axes[0, 1].legend()
        axes[1, 0].plot(estimate.window_time_s, estimate.torque_integral_nm_s, label="reconstructed torque integral")
        axes[1, 0].plot(estimate.window_time_s, estimate.fitted_integral_nm_s, "--", label="J delta(speed) + B integral(speed)")
        axes[1, 0].set_ylabel("Integrated torque [N m s]")
        axes[1, 0].legend(fontsize=8)
        truth = {r["parameter"]: r["true_value"] for r in result["parameter_rows"]}
        for k, name in enumerate(("J", "B")):
            axes[1, 1].plot(estimate.convergence_time_s,
                            100*(estimate.convergence_parameters[:, k]/truth[name]-1), label=name)
        axes[1, 1].axhline(0, color="gray", linestyle=":")
        axes[1, 1].set_ylabel("Cumulative fit error [%], truth for scoring only")
        axes[1, 1].legend()
        for ax in axes.flat:
            ax.set_xlabel("Time [s]")
            ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(output_dir / "mechanical_identification.png", dpi=160)
        plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for name, sim in result["simulations"].items():
        axes[0, 0].plot(sim["time"], sim["rpm"], label=name)
        post = sim["time"] >= 0.29
        axes[0, 1].plot(sim["time"][post], sim["rpm"][post]-1000, label=name)
        axes[1, 0].plot(sim["time"][post], (sim["iq"]-sim["iq_ref"])[post], label=name)
        axes[1, 1].plot(sim["time"], sim["voltage_magnitude"], label=name)
    axes[0, 0].set_ylabel("Speed [rpm]")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].set_ylabel("Post-load speed error [rpm]")
    axes[1, 0].set_ylabel("Post-load iq tracking error [A]")
    axes[1, 1].set_ylabel("Applied voltage magnitude [V]")
    axes[1, 1].axhline(next(iter(result["simulations"].values()))["voltage_limit"], linestyle=":", color="gray")
    for ax in axes.flat:
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "full_commissioning_recovery.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    result = run_experiment()
    save_results(result)
    print(json.dumps({"parameters": result["parameter_rows"], "performance": result["performance"],
                      "mechanical_quality": asdict(result["full"].mechanical.quality)}, indent=2))
