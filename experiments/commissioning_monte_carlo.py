"""Run and plot stratified Monte Carlo validation of self-commissioning."""

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

from src.monte_carlo import MonteCarloConfig, PARAMETERS, run_population, summarize_population


def _plot_parameter_errors(rows, path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    data = [np.asarray([
        abs(row[f"error_{name}_percent"])
        for row in rows if row[f"error_{name}_percent"] is not None
    ]) for name in PARAMETERS]
    data = [np.maximum(values, 1e-6) for values in data]
    if any(len(values) for values in data):
        ax.boxplot(data, tick_labels=PARAMETERS, showfliers=True)
        ax.axhline(10, color="tab:red", linestyle="--", label="10% accuracy threshold")
        ax.set_yscale("log")
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No completed parameter estimates", ha="center",
                va="center", transform=ax.transAxes)
    ax.set_ylabel("Absolute parameter error [%]")
    ax.set_title("Parameter errors for completed estimations"
                 f" ({sum(row['status'] == 'estimator_failed' for row in rows)} estimator failures retained separately)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_control_recovery(rows, path):
    import matplotlib.pyplot as plt

    completed = [row for row in rows if row["status"] == "completed"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, metric, title, unit in (
        (axes[0, 0], "speed_rmse_rpm", "Post-load speed tracking", "rpm"),
        (axes[0, 1], "iq_tracking_rmse_a", "Post-load iq tracking", "A"),
        (axes[1, 0], "recovery_time_s", "Disturbance recovery", "s"),
        (axes[1, 1], "saturation_fraction", "Voltage saturation", "fraction"),
    ):
        finite = [row for row in completed if np.isfinite(row[f"mismatched_{metric}"])
                  and np.isfinite(row[f"commissioned_{metric}"])]
        before = np.asarray([row[f"mismatched_{metric}"] for row in finite])
        after = np.asarray([row[f"commissioned_{metric}"] for row in finite])
        colors = ["tab:orange" if row["voltage_feasible"] else "tab:red" for row in finite]
        ax.scatter(before, after, c=colors, alpha=0.75, edgecolors="none")
        if len(finite):
            upper = max(np.max(before), np.max(after)) * 1.05
            upper = max(upper, 0.01 if metric == "saturation_fraction" else 1e-6)
            ax.plot([0, upper], [0, upper], color="black", linestyle="--", linewidth=1)
            ax.set_xlim(0, upper)
            ax.set_ylim(0, upper)
            if metric in ("speed_rmse_rpm", "iq_tracking_rmse_a"):
                threshold = 1.0 if metric == "speed_rmse_rpm" else 0.001
                ax.set_xscale("symlog", linthresh=threshold)
                ax.set_yscale("symlog", linthresh=threshold)
        ax.set_title(f"{title} (n={len(finite)})")
        ax.set_xlabel(f"Mismatched [{unit}]")
        ax.set_ylabel(f"Commissioned [{unit}]")
        ax.grid(alpha=0.3)
    fig.suptitle("Paired performance: orange = steady-state voltage feasible, red = infeasible\n"
                 "Missing paired points remain in the case CSV and summary counts")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _heatmap(ax, rows, x_key, y_key, x_values, y_values, failure_kind):
    values = np.full((len(y_values), len(x_values)), np.nan)
    counts = np.zeros_like(values, dtype=int)
    for iy, y in enumerate(y_values):
        for ix, x in enumerate(x_values):
            cell = [row for row in rows if row[x_key] == x and row[y_key] == y]
            counts[iy, ix] = len(cell)
            if cell:
                values[iy, ix] = np.mean([
                    row["status"] == "estimator_failed" if failure_kind == "estimator"
                    else not row["workflow_success"] for row in cell
                ])
            label = "—" if not cell else f"{values[iy, ix]:.0%}\nn={len(cell)}"
            ax.text(ix, iy, label, ha="center", va="center", fontsize=8)
    ax.imshow(values, vmin=0, vmax=1, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(x_values)), [str(v) for v in x_values])
    ax.set_yticks(range(len(y_values)), [str(v) for v in y_values])
    ax.set_xlabel(x_key.replace("_", " "))
    ax.set_ylabel(y_key.replace("_", " "))


def _plot_failure_regions(rows, path):
    import matplotlib.pyplot as plt

    regular = [row for row in rows if row["excitation_scale"] > 0]
    noise = list(dict.fromkeys(row["noise"] for row in regular))
    speed = sorted(set(row["commissioning_speed_rpm"] for row in regular))
    bus = sorted(set(row["dc_bus_voltage_v"] for row in regular))
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    combinations = (
        ("commissioning_speed_rpm", "noise", speed, noise),
        ("dc_bus_voltage_v", "noise", bus, noise),
        ("dc_bus_voltage_v", "commissioning_speed_rpm", bus, speed),
    )
    for row_axes, kind in zip(axes, ("estimator", "workflow")):
        for ax, (x_key, y_key, x_values, y_values) in zip(row_axes, combinations):
            _heatmap(ax, regular, x_key, y_key, x_values, y_values, kind)
            ax.set_title(f"{kind.capitalize()} failure rate")
    fig.suptitle("Failure regions by noise, commissioning speed, and control DC bus\n"
                 "Pairwise cells pool the remaining factor; deliberate zero-excitation case excluded")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_results(rows, summary, output_dir=Path("results")):
    """Write all cases, aggregate statistics, and three comparison figures."""
    if not rows:
        raise ValueError("Cannot save an empty population")
    matplotlib.use("Agg")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_path = output_dir / "commissioning_monte_carlo_cases.csv"
    with cases_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary_path = output_dir / "commissioning_monte_carlo_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    errors_path = output_dir / "commissioning_monte_carlo_errors.png"
    recovery_path = output_dir / "commissioning_monte_carlo_recovery.png"
    regions_path = output_dir / "commissioning_monte_carlo_failure_regions.png"
    _plot_parameter_errors(rows, errors_path)
    _plot_control_recovery(rows, recovery_path)
    _plot_failure_regions(rows, regions_path)
    return cases_path, summary_path, errors_path, recovery_path, regions_path


def main():
    config = MonteCarloConfig()
    rows = run_population(config)
    summary = summarize_population(rows)
    print(f'{summary["success_count"]}/{summary["total_cases"]} workflow successes '
          f'({summary["success_rate"]:.1%}); '
          f'{summary["estimator_failure_count"]} estimator failures')
    for name in ("speed_rmse_rpm", "iq_tracking_rmse_a"):
        paired = summary["paired_metrics"][name]
        print(f'{name}: paired n={paired["n_pairs"]}, '
              f'mismatched median={paired["mismatched"]["median"]}, '
              f'commissioned median={paired["commissioned"]["median"]}')
    for path in save_results(rows, summary):
        print(path)


if __name__ == "__main__":
    main()
