"""One accepted simulated commissioning result -> C header -> quantified parity."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import matplotlib
from experiments.operating_feasibility import write_csv
from firmware.parity import FLAGS, ROOT, SOURCES, compile_core, compiler_path, run_parity
from src.commissioning import commission_from_measurements
from src.firmware_config import build_firmware_config, export_c_header
from src.full_commissioning import complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.motor import PMSMParameters
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements


OUTPUT = ROOT/"results/firmware_parity"


def commissioned_example():
    # Simulator owns this plant. The exporter receives ONLY the full result.
    plant = PMSMParameters(Rs=.5, Ld=.0012, Lq=.0009, psi_f=.022, J=.00055, B=.0002)
    ec = ExcitationConfig(current_noise_std_a=.01, voltage_noise_std_v=.01, speed_noise_std_rad_s=.02, seed=1801)
    rc = RotatingExcitationConfig(q_voltage_base_v=5, current_noise_std_a=.01,
                                 voltage_noise_std_v=.01, speed_noise_std_rad_s=.02, seed=1802)
    electrical = commission_from_measurements(simulate_locked_rotor_measurements(plant, ec),
        simulate_driven_rotor_measurements(plant, rc), plant.pole_pairs)
    if not electrical.quality.accepted:
        raise RuntimeError(f"Demo electrical commissioning rejected: {electrical.quality.rejection_reasons}")
    prior = PMSMParameters()
    mechanical = simulate_mechanical_measurements(plant, electrical.retuned_controller_parameters(prior),
        MechanicalExcitationConfig(dc_bus_voltage_v=24, seed=1803)).measurements
    full = complete_commissioning(electrical, mechanical)
    if not full.quality.accepted:
        raise RuntimeError(f"Demo full commissioning rejected: {full.quality.rejection_reasons}")
    return full, full.retuned_controller_parameters(prior), plant


def compile_c_tests(directory, header_dir, compiler=None):
    compiler = compiler or compiler_path()
    path = Path(directory)/("test_core.exe" if sys.platform == "win32" else "test_core")
    command = [compiler, *FLAGS, "-I", str(ROOT/"firmware/include"), "-I", str(header_dir),
        *(str(s) for s in SOURCES), str(ROOT/"firmware/tests/test_core.c"), "-lm", "-o", str(path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return subprocess.check_output([str(path)], text=True).strip()


def plot_trace(trace, output):
    import matplotlib.pyplot as plt
    t = [r["time_s"] for r in trace]
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for n, ax in zip(("vd", "vq", "iq_ref"), axes):
        ax.plot(t, [r["python_"+n] for r in trace], label="Python float64", color="tab:blue")
        ax.plot(t, [r["c_"+n] for r in trace], label="C float32", linestyle="--", color="tab:orange")
        error_axis = ax.twinx()
        error_axis.plot(t, [r["error_"+n] for r in trace], color="tab:green", alpha=.7, label="Absolute difference")
        error_axis.set_ylabel("Absolute difference [V]" if n != "iq_ref" else "Absolute difference [A]", color="tab:green")
        ax.set_ylabel(n+(" [V]" if n != "iq_ref" else " [A]"))
        ax.grid(alpha=.3)
        ax.legend(loc="upper left", fontsize=8)
    axes[-1].set_xlabel("Replay input time [s]")
    fig.suptitle("M18 identical-input controller replay — no C motor plant\nAll 30,000 steps compared; plotted samples include every signal's maximum absolute/relative error")
    fig.tight_layout()
    fig.savefig(output/"parity_plot.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    matplotlib.use("Agg")
    if compiler_path() is None:
        raise SystemExit("A GCC/Clang compiler is required to generate parity evidence; set PMSM_CC")
    full, params, plant = commissioned_example()
    config = build_firmware_config(full, dc_bus_voltage_v=24)
    args.output.mkdir(parents=True, exist_ok=True)
    export_c_header(config, args.output/"generated_motor_config.h",
        provenance="SIMULATED accepted full commissioning, M18 seeds 1801/1802/1803; not universal motor constants.")
    with tempfile.TemporaryDirectory(prefix="pmsm-parity-") as directory:
        core, build = compile_core(directory)
        try:
            summary, vectors, trace = run_parity(core, full, params, plant)
            c_tests = compile_c_tests(directory, args.output)
        finally:
            core.close()
    summary.update(build=build, c_tests=c_tests, generated_configuration=asdict(config),
        commissioning=dict(electrical_accepted=full.electrical.quality.accepted,
            mechanical_accepted=full.mechanical.quality.accepted, full_accepted=full.quality.accepted,
            seeds=[1801, 1802, 1803], source="Simulated sampled identification, no oracle export"),
        comparison="Unmodified Python float64 algorithms versus C float32; identical quantized input streams")
    write_csv(args.output/"parity_vectors.csv", vectors)
    write_csv(args.output/"parity_trace.csv", trace)
    (args.output/"parity_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    plot_trace(trace, args.output)
    print(json.dumps(dict(build=build, c_tests=c_tests, compared_samples=summary["total_compared_samples"],
        worst_absolute=summary["worst_absolute"], flags={k:v for k,v in summary["saturation_flags"].items() if k!="boundary_probes"},
        secondary_binary32=summary["secondary_binary32_foc_max_absolute_errors"]), indent=2))


if __name__ == "__main__":
    main()
