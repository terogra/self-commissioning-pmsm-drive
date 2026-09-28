"""Permanent-magnet flux estimation from a driven-rotor dq experiment.

The q-axis equation is vq = Rs*iq + Lq*d(iq)/dt + omega_e*(Ld*id + psi_f).
Integrating over a window and using previously identified Rs/Ld/Lq leaves
psi_f as the only regression coefficient. The estimator sees measurements,
not the PMSM plant or its true flux linkage.
"""

from dataclasses import dataclass

import numpy as np

from src.identification import ElectricalEstimate, _integer_ratio
from src.motor import PMSMModel, PMSMParameters
from src.identification_quality import MeasurementNoise, RegressionDiagnostics, flux_diagnostics


@dataclass(frozen=True)
class RotatingExcitationConfig:
    duration_s: float = 0.3
    integration_dt_s: float = 20e-6
    sample_dt_s: float = 100e-6
    speed_rpm: float = 600.0
    d_hold_samples: int = 19
    q_hold_samples: int = 29
    d_voltage_v: float = 0.7
    q_voltage_base_v: float = 8.0
    q_voltage_perturb_v: float = 0.7
    dc_bus_voltage_v: float = 24.0
    current_noise_std_a: float = 0.0
    voltage_noise_std_v: float = 0.0
    speed_noise_std_rad_s: float = 0.0
    seed: int = 17


@dataclass(frozen=True)
class RotatingMeasurements:
    time_s: np.ndarray
    current_d_a: np.ndarray
    current_q_a: np.ndarray
    speed_rad_s: np.ndarray
    voltage_d_v: np.ndarray
    voltage_q_v: np.ndarray
    noise: MeasurementNoise | None = None


@dataclass(frozen=True)
class FluxEstimate:
    psi_f: float
    regression_rmse_v_s: float
    window_time_s: np.ndarray
    observed_back_emf_integral_v_s: np.ndarray
    fitted_back_emf_integral_v_s: np.ndarray
    convergence_time_s: np.ndarray
    convergence_psi_f: np.ndarray
    diagnostics: RegressionDiagnostics | None = None


def simulate_driven_rotor_measurements(
    plant_params: PMSMParameters,
    config: RotatingExcitationConfig = RotatingExcitationConfig(),
) -> RotatingMeasurements:
    """Simulate sampled electrical data with rotor speed imposed by a drive rig.

    The voltage program has a fixed q-axis bias independent of true psi_f and
    independent bipolar d/q perturbations. The imposed mechanical speed is
    held by an external prime mover; only the plant's electrical states evolve.
    """
    samples = _integer_ratio(config.duration_s, config.sample_dt_s, "duration/sample")
    substeps = _integer_ratio(config.sample_dt_s, config.integration_dt_s, "sample/integration")
    if any(not isinstance(value, int) or value < 1 for value in
           (config.d_hold_samples, config.q_hold_samples)):
        raise ValueError("Voltage hold durations must be positive integers")
    values = (
        config.speed_rpm, config.d_voltage_v, config.q_voltage_base_v,
        config.q_voltage_perturb_v, config.dc_bus_voltage_v,
        config.current_noise_std_a, config.voltage_noise_std_v,
        config.speed_noise_std_rad_s,
    )
    if not np.all(np.isfinite(values)) or config.dc_bus_voltage_v <= 0:
        raise ValueError("Speed, voltage, and noise settings must be finite")
    if any(value < 0 for value in (
        config.current_noise_std_a, config.voltage_noise_std_v,
        config.speed_noise_std_rad_s,
    )):
        raise ValueError("Measurement noise standard deviations must be nonnegative")
    if abs(config.speed_rpm) < 100.0:
        raise ValueError("Rotating excitation requires at least 100 rpm")
    if np.hypot(config.d_voltage_v,
                abs(config.q_voltage_base_v) + abs(config.q_voltage_perturb_v)) > (
        config.dc_bus_voltage_v / np.sqrt(3.0)
    ):
        raise ValueError("Excitation exceeds the linear SVPWM voltage limit")

    rng = np.random.default_rng(config.seed)
    d_signs = rng.choice((-1.0, 1.0), size=(samples - 1) // config.d_hold_samples + 1)
    q_signs = rng.choice((-1.0, 1.0), size=(samples - 1) // config.q_hold_samples + 1)
    voltage_d = config.d_voltage_v * d_signs[np.arange(samples) // config.d_hold_samples]
    voltage_q = (
        config.q_voltage_base_v
        + config.q_voltage_perturb_v * q_signs[np.arange(samples) // config.q_hold_samples]
    )

    motor = PMSMModel(plant_params)
    true_speed = config.speed_rpm * 2 * np.pi / 60
    currents = np.zeros((samples + 1, 2))

    def electrical_derivative(current, vd, vq):
        state = np.array([current[0], current[1], true_speed, 0.0])
        return motor.derivatives(state, vd, vq, 0.0)[:2]

    dt = config.integration_dt_s
    for k in range(samples):
        current = currents[k].copy()
        vd, vq = voltage_d[k], voltage_q[k]
        for _ in range(substeps):
            k1 = electrical_derivative(current, vd, vq)
            k2 = electrical_derivative(current + 0.5 * dt * k1, vd, vq)
            k3 = electrical_derivative(current + 0.5 * dt * k2, vd, vq)
            k4 = electrical_derivative(current + dt * k3, vd, vq)
            current += (dt / 6) * (k1 + 2 * k2 + 2 * k3 + k4)
        currents[k + 1] = current

    return RotatingMeasurements(
        time_s=np.arange(samples + 1) * config.sample_dt_s,
        current_d_a=currents[:, 0] + rng.normal(0, config.current_noise_std_a, samples + 1),
        current_q_a=currents[:, 1] + rng.normal(0, config.current_noise_std_a, samples + 1),
        speed_rad_s=true_speed + rng.normal(0, config.speed_noise_std_rad_s, samples + 1),
        voltage_d_v=voltage_d + rng.normal(0, config.voltage_noise_std_v, samples),
        voltage_q_v=voltage_q + rng.normal(0, config.voltage_noise_std_v, samples),
        noise=MeasurementNoise(config.current_noise_std_a, config.voltage_noise_std_v,
                               config.speed_noise_std_rad_s),
    )


def _window_integrals(signal, dt, starts, ends):
    interval_area = 0.5 * (signal[:-1] + signal[1:]) * dt
    cumulative = np.concatenate(([0.0], np.cumsum(interval_area)))
    return cumulative[ends] - cumulative[starts]


def estimate_flux_linkage(
    data: RotatingMeasurements,
    electrical: ElectricalEstimate,
    pole_pairs: int,
    window_samples: int = 10,
    min_abs_speed_rad_s: float = 10.0,
) -> FluxEstimate:
    """Fit psi_f from integrated rotating q-axis voltage balance.

    For each window, y = integral(vq - Rs*iq - omega_e*Ld*id) dt
    - Lq*Delta(iq), and x = integral(omega_e) dt. Least squares fits y=x*psi_f.
    """
    time = np.asarray(data.time_s)
    n = len(time) - 1
    signals = (data.current_d_a, data.current_q_a, data.speed_rad_s,
               data.voltage_d_v, data.voltage_q_v)
    if n < 2 or any(len(signal) != expected for signal, expected in zip(
        signals, (n + 1, n + 1, n + 1, n, n)
    )):
        raise ValueError("Measurement array lengths do not match sampled intervals")
    if any(not np.all(np.isfinite(signal)) for signal in (time, *signals)):
        raise ValueError("Measurements must be finite")
    intervals = np.diff(time)
    if np.any(intervals <= 0) or not np.allclose(intervals, intervals[0], rtol=1e-9, atol=0):
        raise ValueError("Measurements require uniform increasing sample times")
    if not isinstance(pole_pairs, int) or pole_pairs < 1:
        raise ValueError("pole_pairs must be a positive integer")
    if any(not np.isfinite(value) or value <= 0 for value in
           (electrical.Rs, electrical.Ld, electrical.Lq)):
        raise ValueError("Previously identified Rs/Ld/Lq must be positive and finite")
    if not np.isfinite(min_abs_speed_rad_s) or min_abs_speed_rad_s <= 0:
        raise ValueError("Minimum identification speed must be positive and finite")
    speed = data.speed_rad_s
    if np.min(np.abs(speed)) < min_abs_speed_rad_s or np.any(np.sign(speed) != np.sign(speed[0])):
        raise ValueError("Flux linkage requires sustained nonzero measured speed")
    if not isinstance(window_samples, int) or window_samples < 1 or n // window_samples < 2:
        raise ValueError("Need at least two complete integration windows")

    starts = np.arange(0, n - window_samples + 1, window_samples)
    ends = starts + window_samples
    dt = intervals[0]
    omega_e = pole_pairs * speed
    speed_area = _window_integrals(omega_e, dt, starts, ends)
    q_current_area = _window_integrals(data.current_q_a, dt, starts, ends)
    cross_area = _window_integrals(omega_e * data.current_d_a, dt, starts, ends)
    voltage_cumulative = np.concatenate(([0.0], np.cumsum(data.voltage_q_v * dt)))
    voltage_area = voltage_cumulative[ends] - voltage_cumulative[starts]
    observed = (
        voltage_area - electrical.Rs * q_current_area
        - electrical.Lq * (data.current_q_a[ends] - data.current_q_a[starts])
        - electrical.Ld * cross_area
    )
    denominator = float(np.dot(speed_area, speed_area))
    psi_f = float(np.dot(speed_area, observed) / denominator)
    if not np.isfinite(psi_f) or psi_f <= 0:
        raise ValueError("Estimated flux linkage must be positive and finite")
    convergence = np.cumsum(speed_area * observed) / np.cumsum(speed_area ** 2)
    residual = observed - speed_area * psi_f
    return FluxEstimate(
        psi_f=psi_f,
        regression_rmse_v_s=float(np.sqrt(np.mean(residual ** 2))),
        window_time_s=time[ends],
        observed_back_emf_integral_v_s=observed,
        fitted_back_emf_integral_v_s=speed_area * psi_f,
        convergence_time_s=time[ends],
        convergence_psi_f=convergence,
        diagnostics=flux_diagnostics(data, electrical, pole_pairs, psi_f, speed_area,
                                     observed, starts, ends, q_current_area, cross_area),
    )
