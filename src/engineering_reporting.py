"""Plot measurement fits and simulated control responses."""

import numpy as np
from matplotlib.figure import Figure


def control_figure(result):
    fig = Figure(figsize=(12, 10), layout="constrained")
    if result.control is None:
        ax = fig.subplots()
        ax.axis("off")
        ax.text(.05, .8, result.status, fontsize=20, transform=ax.transAxes)
        ax.text(.05, .65, "\n".join(result.quality.rejection_reasons), wrap=True, transform=ax.transAxes)
        message = ("Control validation unavailable; accepted controller update retained.\n"
                   + "\n".join(result.warnings) if result.quality.accepted else
                   "Prior controller retained.\nCommissioned operation and firmware export unavailable.")
        ax.text(.05, .4, message, wrap=True, transform=ax.transAxes)
        return fig
    data = result.control.trace
    stride = max(1, len(data["time"])//2000)
    transitions = [np.flatnonzero(np.diff(data[flag].astype(int)))+1
                   for flag in ("voltage_saturated", "actual_bus_saturated")]
    index = np.unique(np.concatenate([np.arange(0, len(data["time"]), stride),
                                     [len(data["time"])-1], *transitions]))
    time = data["time"][index]
    axes = fig.subplots(3, 2).ravel()
    def plot(ax, key, label, **kwargs):
        ax.plot(time, data[key][index], label=label, **kwargs)
    plot(axes[0], "rpm", "Simulated true speed")
    axes[0].axhline(data["speed_ref_rpm"], ls="--", color="black", label="Reference")
    axes[0].set_ylabel("Speed [rpm]")
    plot(axes[1], "id", "True id")
    plot(axes[1], "measured_id", "Measured id", ls="--")
    axes[1].set_ylabel("d current [A]")
    plot(axes[2], "iq", "True iq")
    plot(axes[2], "measured_iq", "Measured iq", ls="--")
    plot(axes[2], "iq_ref_true", "Reference mapped to true frame", ls=":")
    plot(axes[2], "iq_ref", "Controller-frame reference", ls="-.")
    axes[2].set_ylabel("q current [A]")
    plot(axes[3], "torque", "True electromagnetic torque")
    plot(axes[3], "load_torque", "External load", ls="--")
    axes[3].set_ylabel("Torque [N m]")
    plot(axes[4], "requested_voltage_magnitude", "Requested dq magnitude")
    plot(axes[4], "voltage_magnitude", "Applied terminal magnitude", ls="--")
    command = np.hypot(data["command_voltage_d"], data["command_voltage_q"])
    axes[4].plot(time, command[index], label="Limited FOC command", ls=":")
    axes[4].axhline(data["voltage_limit"], color="black", ls="--", label="Nominal bus limit")
    axes[4].axhline(data["actual_voltage_limit"], color="red", ls=":", label="Actual bus limit")
    axes[4].set_ylabel("Voltage magnitude [V]")
    plot(axes[5], "voltage_saturated", "Nominal FOC saturation")
    plot(axes[5], "actual_bus_saturated", "Actual-bus clipping", ls=":")
    axes[5].set_ylabel("Saturation state [0/1]")
    for ax in axes:
        ax.set_xlabel("Simulation time [s]")
        ax.grid(alpha=.25)
        ax.legend(fontsize=7)
    fig.suptitle(f"Current-run simulation evaluation / ground truth — {result.config.scenario}, seed {result.config.seed}\n"
                 "Plots sampled for display; metrics use the full trace")
    return fig


def commissioning_figure(record, estimate):
    fig = Figure(figsize=(10, 4), layout="constrained")
    measured, fitted = fig.subplots(1, 2)
    data = record.measurements
    if data is None:
        measured.text(.05, .5, record.measurement_failure or "No measurements", transform=measured.transAxes)
        return fig
    measured.plot(data.time_s, data.current_d_a, label="Measured id")
    measured.plot(data.time_s, data.current_q_a, label="Measured iq")
    measured.set(xlabel="Sample time [s]", ylabel="Current [A]")
    speed = measured.twinx()
    speed.plot(data.time_s, data.speed_rad_s, color="gray", alpha=.4, label="Measured speed")
    speed.set_ylabel("Measured speed [rad/s]")
    measured.legend(fontsize=8)
    if estimate is None:
        fitted.text(.05, .5, "No fitted model available", transform=fitted.transAxes)
    elif record.stage.value == "rotating":
        fitted.plot(estimate.window_time_s, estimate.observed_back_emf_integral_v_s, label="Observed back-EMF integral")
        fitted.plot(estimate.window_time_s, estimate.fitted_back_emf_integral_v_s, "--", label="Fitted")
        fitted.set(xlabel="Window time [s]", ylabel="Back-EMF integral [V s]")
        fitted.legend(fontsize=8)
    elif record.stage.value == "mechanical":
        fitted.plot(estimate.window_time_s, estimate.torque_integral_nm_s, label="Reconstructed torque integral")
        fitted.plot(estimate.window_time_s, estimate.fitted_integral_nm_s, "--", label="Fitted J/B model")
        fitted.set(xlabel="Window time [s]", ylabel="Torque integral [N m s]")
        fitted.legend(fontsize=8)
    else:
        # Each coefficient has its own units; normalize only for a convergence view.
        final = np.array([estimate.Rs, estimate.Ld, estimate.Lq])
        fitted.plot(estimate.convergence_time_s, estimate.convergence_parameters/final, label=["Rs", "Ld", "Lq"])
        fitted.set(xlabel="Prefix-fit time [s]", ylabel="Estimate / final estimate [dimensionless]")
        fitted.legend(fontsize=8)
    for ax in (measured, fitted): ax.grid(alpha=.25)
    fig.suptitle(f"Estimator-visible data — {record.stage.value}, attempt {record.number}")
    return fig
