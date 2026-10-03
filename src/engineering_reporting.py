"""Engineering figures from computed records; no estimator or tuning equations."""

import numpy as np
from matplotlib.figure import Figure


_TR = {
    "Simulated true speed": "Simüle edilen gerçek hız",
    "Reference": "Referans",
    "Speed [rpm]": "Hız [rpm]",
    "True id": "Gerçek id",
    "Measured id": "Ölçülen id",
    "d current [A]": "d ekseni akımı [A]",
    "True iq": "Gerçek iq",
    "Measured iq": "Ölçülen iq",
    "Reference mapped to true frame": "Gerçek çerçeveye taşınmış referans",
    "Controller-frame reference": "Denetleyici çerçevesi referansı",
    "q current [A]": "q ekseni akımı [A]",
    "True electromagnetic torque": "Gerçek elektromanyetik moment",
    "External load": "Harici yük",
    "Torque [N m]": "Moment [N m]",
    "Requested dq magnitude": "İstenen dq gerilim büyüklüğü",
    "Applied terminal magnitude": "Uygulanan terminal gerilim büyüklüğü",
    "Limited FOC command": "Sınırlandırılmış FOC komutu",
    "Nominal bus limit": "Nominal bara sınırı",
    "Actual bus limit": "Gerçek bara sınırı",
    "Voltage magnitude [V]": "Gerilim büyüklüğü [V]",
    "Nominal FOC saturation": "Nominal FOC doygunluğu",
    "Actual-bus clipping": "Gerçek bara kırpması",
    "Saturation state [0/1]": "Doygunluk durumu [0/1]",
    "Simulation time [s]": "Simülasyon zamanı [s]",
    "Current-run simulation evaluation / ground truth": "Mevcut çalışma simülasyon değerlendirmesi / gerçek değer",
    "Plots sampled for display; metrics use the full trace": "Grafikler gösterim için örneklenmiştir; metrikler tam izi kullanır",
    "Control validation unavailable; accepted controller update retained.": "Kontrol doğrulaması kullanılamıyor; kabul edilen denetleyici güncellemesi korunuyor.",
    "Prior controller retained.": "Başlangıç denetleyicisi korundu.",
    "Commissioned operation and firmware export unavailable.": "Devreye alınmış çalışma ve firmware dışa aktarımı kullanılamıyor.",
    "No measurements": "Ölçüm yok",
    "Measured speed": "Ölçülen hız",
    "Sample time [s]": "Örnek zamanı [s]",
    "Current [A]": "Akım [A]",
    "Measured speed [rad/s]": "Ölçülen hız [rad/s]",
    "No fitted model available": "Kestirilmiş model yok",
    "Observed back-EMF integral": "Gözlenen ters EMK integrali",
    "Fitted": "Kestirilen",
    "Window time [s]": "Pencere zamanı [s]",
    "Back-EMF integral [V s]": "Ters EMK integrali [V s]",
    "Reconstructed torque integral": "Yeniden oluşturulan moment integrali",
    "Fitted J/B model": "Kestirilen J/B modeli",
    "Torque integral [N m s]": "Moment integrali [N m s]",
    "Prefix-fit time [s]": "Kısmi kestirim zamanı [s]",
    "Estimate / final estimate [dimensionless]": "Kestirim / son kestirim [boyutsuz]",
    "Estimator-visible data": "Kestiricinin görebildiği veriler",
    "attempt": "deneme",
    "standstill": "duran rotor",
    "rotating": "dönen rotor",
    "mechanical": "mekanik",
}


def _label(language, value):
    return _TR.get(value, value) if language == "tr" else value


def control_figure(result, language="en"):
    fig = Figure(figsize=(12, 10), layout="constrained")
    if result.control is None:
        ax = fig.subplots()
        ax.axis("off")
        ax.text(.05, .8, result.status, fontsize=20, transform=ax.transAxes)
        ax.text(.05, .65, "\n".join(result.quality.rejection_reasons), wrap=True, transform=ax.transAxes)
        if result.quality.accepted:
            message = _label(language, "Control validation unavailable; accepted controller update retained.")
            if result.warnings:
                message += "\n" + "\n".join(result.warnings)
        else:
            message = (
                _label(language, "Prior controller retained.") + "\n"
                + _label(language, "Commissioned operation and firmware export unavailable.")
            )
        ax.text(.05, .4, message, wrap=True, transform=ax.transAxes)
        return fig

    data = result.control.trace
    stride = max(1, len(data["time"])//2000)
    transitions = [
        np.flatnonzero(np.diff(data[flag].astype(int)))+1
        for flag in ("voltage_saturated", "actual_bus_saturated")
    ]
    index = np.unique(np.concatenate([
        np.arange(0, len(data["time"]), stride),
        [len(data["time"])-1],
        *transitions,
    ]))
    time = data["time"][index]
    axes = fig.subplots(3, 2).ravel()

    def plot(ax, key, label, **kwargs):
        ax.plot(time, data[key][index], label=_label(language, label), **kwargs)

    plot(axes[0], "rpm", "Simulated true speed")
    axes[0].axhline(data["speed_ref_rpm"], ls="--", color="black", label=_label(language, "Reference"))
    axes[0].set_ylabel(_label(language, "Speed [rpm]"))

    plot(axes[1], "id", "True id")
    plot(axes[1], "measured_id", "Measured id", ls="--")
    axes[1].set_ylabel(_label(language, "d current [A]"))

    plot(axes[2], "iq", "True iq")
    plot(axes[2], "measured_iq", "Measured iq", ls="--")
    plot(axes[2], "iq_ref_true", "Reference mapped to true frame", ls=":")
    plot(axes[2], "iq_ref", "Controller-frame reference", ls="-.")
    axes[2].set_ylabel(_label(language, "q current [A]"))

    plot(axes[3], "torque", "True electromagnetic torque")
    plot(axes[3], "load_torque", "External load", ls="--")
    axes[3].set_ylabel(_label(language, "Torque [N m]"))

    plot(axes[4], "requested_voltage_magnitude", "Requested dq magnitude")
    plot(axes[4], "voltage_magnitude", "Applied terminal magnitude", ls="--")
    command = np.hypot(data["command_voltage_d"], data["command_voltage_q"])
    axes[4].plot(time, command[index], label=_label(language, "Limited FOC command"), ls=":")
    axes[4].axhline(data["voltage_limit"], color="black", ls="--", label=_label(language, "Nominal bus limit"))
    axes[4].axhline(data["actual_voltage_limit"], color="red", ls=":", label=_label(language, "Actual bus limit"))
    axes[4].set_ylabel(_label(language, "Voltage magnitude [V]"))

    plot(axes[5], "voltage_saturated", "Nominal FOC saturation")
    plot(axes[5], "actual_bus_saturated", "Actual-bus clipping", ls=":")
    axes[5].set_ylabel(_label(language, "Saturation state [0/1]"))

    for ax in axes:
        ax.set_xlabel(_label(language, "Simulation time [s]"))
        ax.grid(alpha=.25)
        ax.legend(fontsize=7)

    fig.suptitle(
        f"{_label(language, 'Current-run simulation evaluation / ground truth')} — "
        f"{result.config.scenario}, seed {result.config.seed}\n"
        f"{_label(language, 'Plots sampled for display; metrics use the full trace')}"
    )
    return fig


def commissioning_figure(record, estimate, language="en"):
    fig = Figure(figsize=(10, 4), layout="constrained")
    measured, fitted = fig.subplots(1, 2)
    data = record.measurements
    if data is None:
        measured.text(
            .05,
            .5,
            record.measurement_failure or _label(language, "No measurements"),
            transform=measured.transAxes,
        )
        return fig

    measured.plot(data.time_s, data.current_d_a, label=_label(language, "Measured id"))
    measured.plot(data.time_s, data.current_q_a, label=_label(language, "Measured iq"))
    measured.set(
        xlabel=_label(language, "Sample time [s]"),
        ylabel=_label(language, "Current [A]"),
    )
    speed = measured.twinx()
    speed.plot(
        data.time_s,
        data.speed_rad_s,
        color="gray",
        alpha=.4,
        label=_label(language, "Measured speed"),
    )
    speed.set_ylabel(_label(language, "Measured speed [rad/s]"))
    measured.legend(fontsize=8)

    if estimate is None:
        fitted.text(.05, .5, _label(language, "No fitted model available"), transform=fitted.transAxes)
    elif record.stage.value == "rotating":
        fitted.plot(
            estimate.window_time_s,
            estimate.observed_back_emf_integral_v_s,
            label=_label(language, "Observed back-EMF integral"),
        )
        fitted.plot(
            estimate.window_time_s,
            estimate.fitted_back_emf_integral_v_s,
            "--",
            label=_label(language, "Fitted"),
        )
        fitted.set(
            xlabel=_label(language, "Window time [s]"),
            ylabel=_label(language, "Back-EMF integral [V s]"),
        )
        fitted.legend(fontsize=8)
    elif record.stage.value == "mechanical":
        fitted.plot(
            estimate.window_time_s,
            estimate.torque_integral_nm_s,
            label=_label(language, "Reconstructed torque integral"),
        )
        fitted.plot(
            estimate.window_time_s,
            estimate.fitted_integral_nm_s,
            "--",
            label=_label(language, "Fitted J/B model"),
        )
        fitted.set(
            xlabel=_label(language, "Window time [s]"),
            ylabel=_label(language, "Torque integral [N m s]"),
        )
        fitted.legend(fontsize=8)
    else:
        final = np.array([estimate.Rs, estimate.Ld, estimate.Lq])
        fitted.plot(
            estimate.convergence_time_s,
            estimate.convergence_parameters/final,
            label=["Rs", "Ld", "Lq"],
        )
        fitted.set(
            xlabel=_label(language, "Prefix-fit time [s]"),
            ylabel=_label(language, "Estimate / final estimate [dimensionless]"),
        )
        fitted.legend(fontsize=8)

    for ax in (measured, fitted):
        ax.grid(alpha=.25)

    stage = _label(language, record.stage.value)
    fig.suptitle(
        f"{_label(language, 'Estimator-visible data')} — {stage}, "
        f"{_label(language, 'attempt')} {record.number}"
    )
    return fig
