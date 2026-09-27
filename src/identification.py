"""Locked-rotor electrical commissioning from sampled terminal measurements.

At omega_m = 0, the dq equations become
    v_d = Rs * i_d + Ld * d(i_d)/dt
    v_q = Rs * i_q + Lq * d(i_q)/dt.
Integrating each equation over non-overlapping sample windows gives a linear
least-squares problem for [Rs, Ld, Lq]. The estimator has no access to the
plant parameter object used to generate the measurements.
"""

from dataclasses import dataclass

import numpy as np

from src.motor import PMSMModel, PMSMParameters


@dataclass(frozen=True)
class ExcitationConfig:
    duration_s: float = 0.4
    integration_dt_s: float = 20e-6
    sample_dt_s: float = 100e-6
    d_hold_samples: int = 23
    q_hold_samples: int = 31
    d_voltage_v: float = 1.2
    q_voltage_v: float = 1.4
    dc_bus_voltage_v: float = 24.0
    current_noise_std_a: float = 0.0
    voltage_noise_std_v: float = 0.0
    speed_noise_std_rad_s: float = 0.0
    seed: int = 7


@dataclass(frozen=True)
class StandstillMeasurements:
    time_s: np.ndarray            # N + 1 sampled instants
    current_d_a: np.ndarray       # N + 1 measured currents
    current_q_a: np.ndarray
    speed_rad_s: np.ndarray       # N + 1 measured mechanical speeds
    voltage_d_v: np.ndarray       # N applied/measured interval voltages
    voltage_q_v: np.ndarray


@dataclass(frozen=True)
class ElectricalEstimate:
    Rs: float
    Ld: float
    Lq: float
    regression_rmse_v_s: float
    scaled_condition_number: float
    convergence_time_s: np.ndarray
    convergence_parameters: np.ndarray  # columns: Rs, Ld, Lq


def _integer_ratio(numerator, denominator, name):
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator <= 0:
        raise ValueError(f"{name} requires finite positive times")
    ratio = numerator / denominator
    rounded = round(ratio)
    if rounded < 1 or not np.isclose(ratio, rounded, rtol=0, atol=1e-9):
        raise ValueError(f"{name} must be a positive integer ratio")
    return rounded


def simulate_locked_rotor_measurements(
    plant_params: PMSMParameters,
    config: ExcitationConfig = ExcitationConfig(),
) -> StandstillMeasurements:
    """Excite the existing PMSM electrical plant with a mechanically locked rotor.

    The fixture holds mechanical speed at zero. Independent bipolar voltage
    sequences are held for different durations on d and q. Voltage magnitudes
    stay inside the linear SVPWM circle. Noise is added only to sampled data.
    """
    samples = _integer_ratio(config.duration_s, config.sample_dt_s, "duration/sample")
    substeps = _integer_ratio(config.sample_dt_s, config.integration_dt_s, "sample/integration")
    if any(
        not isinstance(value, int) or value < 1
        for value in (config.d_hold_samples, config.q_hold_samples)
    ):
        raise ValueError("Voltage hold durations must be positive")
    noise_levels = (
        config.current_noise_std_a,
        config.voltage_noise_std_v,
        config.speed_noise_std_rad_s,
    )
    if any(not np.isfinite(value) or value < 0 for value in noise_levels):
        raise ValueError("Measurement noise standard deviations must be finite and nonnegative")
    if not np.isfinite(config.dc_bus_voltage_v) or config.dc_bus_voltage_v <= 0:
        raise ValueError("dc_bus_voltage_v must be positive and finite")
    if not np.all(np.isfinite((config.d_voltage_v, config.q_voltage_v))):
        raise ValueError("Excitation voltages must be finite")
    if np.hypot(config.d_voltage_v, config.q_voltage_v) > config.dc_bus_voltage_v / np.sqrt(3):
        raise ValueError("Excitation exceeds the linear SVPWM voltage limit")

    rng = np.random.default_rng(config.seed)
    d_signs = rng.choice((-1.0, 1.0), size=(samples - 1) // config.d_hold_samples + 1)
    q_signs = rng.choice((-1.0, 1.0), size=(samples - 1) // config.q_hold_samples + 1)
    voltage_d = config.d_voltage_v * d_signs[np.arange(samples) // config.d_hold_samples]
    voltage_q = config.q_voltage_v * q_signs[np.arange(samples) // config.q_hold_samples]

    motor = PMSMModel(plant_params)
    currents = np.zeros((samples + 1, 2))

    def electrical_derivative(current, vd, vq):
        locked_state = np.array([current[0], current[1], 0.0, 0.0])
        return motor.derivatives(locked_state, vd, vq, 0.0)[:2]

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

    time = np.arange(samples + 1) * config.sample_dt_s
    return StandstillMeasurements(
        time_s=time,
        current_d_a=currents[:, 0] + rng.normal(0, config.current_noise_std_a, samples + 1),
        current_q_a=currents[:, 1] + rng.normal(0, config.current_noise_std_a, samples + 1),
        speed_rad_s=rng.normal(0, config.speed_noise_std_rad_s, samples + 1),
        voltage_d_v=voltage_d + rng.normal(0, config.voltage_noise_std_v, samples),
        voltage_q_v=voltage_q + rng.normal(0, config.voltage_noise_std_v, samples),
    )


def _window_terms(current, voltage, dt, starts, ends):
    current_area = 0.5 * (current[:-1] + current[1:]) * dt
    voltage_area = voltage * dt
    current_cumulative = np.concatenate(([0.0], np.cumsum(current_area)))
    voltage_cumulative = np.concatenate(([0.0], np.cumsum(voltage_area)))
    return (
        current_cumulative[ends] - current_cumulative[starts],
        current[ends] - current[starts],
        voltage_cumulative[ends] - voltage_cumulative[starts],
    )


def _solve_scaled(matrix, target):
    scales = np.linalg.norm(matrix, axis=0)
    if np.any(scales <= 0):
        raise ValueError("Excitation does not identify all three parameters")
    scaled = matrix / scales
    if np.linalg.matrix_rank(scaled) < 3:
        raise ValueError("Excitation does not identify all three parameters")
    estimate = np.linalg.lstsq(scaled, target, rcond=None)[0] / scales
    return estimate, float(np.linalg.cond(scaled))


def estimate_standstill_parameters(
    data: StandstillMeasurements,
    window_samples: int = 10,
    max_abs_speed_rad_s: float = 1.0,
) -> ElectricalEstimate:
    """Fit [Rs, Ld, Lq] from window-integrated measured voltage/current data."""
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
    if (
        not np.isfinite(max_abs_speed_rad_s)
        or max_abs_speed_rad_s <= 0
        or np.max(np.abs(data.speed_rad_s)) > max_abs_speed_rad_s
    ):
        raise ValueError("Locked-rotor identification requires near-zero measured speed")
    if not isinstance(window_samples, int) or window_samples < 1 or n // window_samples < 2:
        raise ValueError("Need at least two complete integration windows")

    starts = np.arange(0, n - window_samples + 1, window_samples)
    ends = starts + window_samples
    d_area, d_change, d_voltage_area = _window_terms(
        data.current_d_a, data.voltage_d_v, intervals[0], starts, ends
    )
    q_area, q_change, q_voltage_area = _window_terms(
        data.current_q_a, data.voltage_q_v, intervals[0], starts, ends
    )
    matrix = np.zeros((2 * len(starts), 3))
    target = np.zeros(2 * len(starts))
    matrix[0::2, 0], matrix[0::2, 1] = d_area, d_change
    matrix[1::2, 0], matrix[1::2, 2] = q_area, q_change
    target[0::2], target[1::2] = d_voltage_area, q_voltage_area

    coefficients, condition_number = _solve_scaled(matrix, target)
    if np.any(coefficients <= 0):
        raise ValueError("Electrical estimates must be positive")
    convergence_time = []
    convergence = []
    for windows in range(2, len(starts) + 1):
        try:
            partial, _ = _solve_scaled(matrix[:2 * windows], target[:2 * windows])
        except ValueError:
            continue
        convergence_time.append(time[ends[windows - 1]])
        convergence.append(partial)

    residual = matrix @ coefficients - target
    return ElectricalEstimate(
        Rs=float(coefficients[0]),
        Ld=float(coefficients[1]),
        Lq=float(coefficients[2]),
        regression_rmse_v_s=float(np.sqrt(np.mean(residual ** 2))),
        scaled_condition_number=condition_number,
        convergence_time_s=np.asarray(convergence_time),
        convergence_parameters=np.asarray(convergence),
    )


def predict_standstill_currents(data: StandstillMeasurements, estimate: ElectricalEstimate):
    """Predict sampled currents from measured interval voltages and fitted R/L."""
    predicted_d = np.empty_like(data.current_d_a)
    predicted_q = np.empty_like(data.current_q_a)
    predicted_d[0], predicted_q[0] = data.current_d_a[0], data.current_q_a[0]
    for k, dt in enumerate(np.diff(data.time_s)):
        alpha_d = np.exp(-estimate.Rs * dt / estimate.Ld)
        alpha_q = np.exp(-estimate.Rs * dt / estimate.Lq)
        predicted_d[k + 1] = (
            alpha_d * predicted_d[k]
            + (1 - alpha_d) * data.voltage_d_v[k] / estimate.Rs
        )
        predicted_q[k + 1] = (
            alpha_q * predicted_q[k]
            + (1 - alpha_q) * data.voltage_q_v[k] / estimate.Rs
        )
    return predicted_d, predicted_q
