"""Separate development and held-out evaluation of the commissioning gate."""

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

import matplotlib
import numpy as np

from src.commissioning_quality import QualityPolicy
from src.monte_carlo import MonteCarloConfig, PARAMETERS, run_population, summarize_population


DEVELOPMENT_SEED = 20261001
EVALUATION_SEED = 20261002


def population_config(population):
    if population == "development":
        return MonteCarloConfig(seed=DEVELOPMENT_SEED, repeats=1,
                                commissioning_speeds_rpm=(150.0, 600.0),
                                dc_bus_voltages_v=(24.0,), excitation_scales=(0.08, 1.0))
    if population == "evaluation":
        return MonteCarloConfig(seed=EVALUATION_SEED, repeats=1, excitation_scales=(0.08, 1.0))
    raise ValueError("Choose development or evaluation")


def _scorable(rows):
    return [r for r in rows if all(r[f"error_{name}_percent"] is not None for name in PARAMETERS)]


def _diagnostic_plot(rows, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    specifications = (
        ("standstill_information_fraction", "Noise / observed regression information", 0.05, PARAMETERS[:3]),
        ("standstill_max_relative_standard_error", "Largest relative sensor-noise SE (standstill)", 0.10 / 3, PARAMETERS[:3]),
        ("standstill_residual_rmse_v_s", "Standstill residual RMS [V s]", None, PARAMETERS[:3]),
        ("rotating_max_relative_standard_error", "Relative sensor-noise SE (flux)", 0.10 / 3, PARAMETERS[3:]),
    )
    for ax, (key, label, threshold, names) in zip(axes.flat, specifications):
        for accepted, color in ((True, "tab:green"), (False, "tab:orange")):
            subset = [r for r in _scorable(rows) if r["quality_accepted"] == accepted and r[key] is not None]
            ax.scatter([max(r[key], 1e-8) for r in subset],
                       [max(max(abs(r[f"error_{name}_percent"]) for name in names), 1e-5) for r in subset],
                       color=color, alpha=0.7, label="accepted" if accepted else "rejected")
        if threshold is not None:
            ax.axvline(threshold, color="black", linestyle=":", label="gate budget")
        ax.axhline(10, color="tab:red", linestyle="--", label="10% scoring criterion")
        ax.set(xscale="log", yscale="log", xlabel=label, ylabel="Largest absolute parameter error [%]")
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Measured diagnostics versus hidden truth (truth used only for scoring)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _error_plot(rows, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(12, 4))
    for ax, name in zip(axes, PARAMETERS):
        values, labels = [], []
        for accepted in (True, False):
            subset = [r for r in _scorable(rows) if r["quality_accepted"] == accepted]
            if subset:
                values.append([max(abs(r[f"error_{name}_percent"]), 1e-5) for r in subset])
                labels.append(f'{"Accepted" if accepted else "Rejected"}\nn={len(subset)}')
        if values:
            ax.boxplot(values, tick_labels=labels)
            ax.set_yscale("log")
        ax.axhline(10, color="tab:red", linestyle="--")
        ax.set_title(name)
        ax.set_ylabel("Absolute error [%]")
        ax.grid(axis="y", alpha=0.3)
    failures = sum(r["status"] == "estimator_failed" for r in rows)
    fig.suptitle(f"Complete parameter estimates; {failures} estimator failures retained in CSV/counts")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _regions_plot(rows, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, xkey, ykey in zip(axes,
                              ("commissioning_speed_rpm", "excitation_scale", "excitation_scale"),
                              ("noise", "noise", "commissioning_speed_rpm")):
        xs = sorted(set(r[xkey] for r in rows))
        ys = list(dict.fromkeys(r[ykey] for r in rows))
        values = np.full((len(ys), len(xs)), np.nan)
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                subset = [r for r in rows if r[xkey] == x and r[ykey] == y]
                if subset:
                    values[j, i] = sum(r["quality_accepted"] for r in subset) / len(subset)
                label = f"{values[j, i]:.0%}\nn={len(subset)}" if subset else "—"
                ax.text(i, j, label, ha="center", va="center", fontsize=8)
        ax.imshow(values, vmin=0, vmax=1, cmap="YlGn", aspect="auto")
        ax.set_xticks(range(len(xs)), [str(x) for x in xs])
        ax.set_yticks(range(len(ys)), [str(y) for y in ys])
        ax.set_xlabel(xkey.replace("_", " "))
        ax.set_ylabel(ykey.replace("_", " "))
    fig.suptitle("Acceptance fraction of ALL cases; remaining factors pooled; none/0 = unexcited sentinel")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _control_plot(rows, path):
    import matplotlib.pyplot as plt

    accepted = [r for r in rows if r["quality_accepted"] and r["status"] == "completed"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, metric, label, threshold in zip(axes,
            ("speed_rmse_rpm", "iq_tracking_rmse_a"), ("Speed RMSE [rpm]", "iq RMSE [A]"), (1.0, 0.001)):
        before = [r[f"mismatched_{metric}"] for r in accepted]
        after = [r[f"commissioned_{metric}"] for r in accepted]
        ax.scatter(before, after, c=["tab:green" if r["workflow_success"] else "tab:red" for r in accepted])
        upper = max(before + after + [threshold]) * 1.05
        ax.plot([0, upper], [0, upper], "k--", linewidth=1)
        ax.set_xscale("symlog", linthresh=threshold)
        ax.set_yscale("symlog", linthresh=threshold)
        ax.set(xlabel=f"Mismatched {label}", ylabel=f"Commissioned {label}", xlim=(0, upper), ylim=(0, upper))
        ax.grid(alpha=0.3)
    fig.suptitle(f"Accepted control runs (n={len(accepted)}); green = workflow success, red = unmet control target")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_results(rows, population, output_dir):
    matplotlib.use("Agg")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_population(rows)
    summary["methodology"] = {
        "population": population, "config": asdict(population_config(population)),
        "policy": asdict(QualityPolicy()),
        "development_seed": DEVELOPMENT_SEED, "evaluation_seed": EVALUATION_SEED,
        "threshold_source": "Pre-specified engineering budgets; no optimization against hidden errors",
        "uncertainty": "First-order sensor-noise sensitivity; excludes EIV bias, no calibrated confidence intervals",
    }
    with (output_dir / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    _diagnostic_plot(rows, output_dir / "diagnostics_vs_error.png")
    _error_plot(rows, output_dir / "accepted_rejected_errors.png")
    _regions_plot(rows, output_dir / "acceptance_regions.png")
    _control_plot(rows, output_dir / "accepted_control_recovery.png")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", choices=("development", "evaluation"), default="evaluation")
    args = parser.parse_args()
    rows = run_population(population_config(args.population))
    summary = save_results(rows, args.population, Path("results/quality_gate") / args.population)
    print(json.dumps(summary["quality_gate"], indent=2))


if __name__ == "__main__":
    main()
