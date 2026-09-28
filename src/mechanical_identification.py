"""Integrated J/B identification from measured speed and reconstructed torque.

This module has no plant dependency. All torques come from measured currents
and the preceding electrical estimates under an explicitly known load.
"""

from dataclasses import dataclass

import numpy as np

from src.commissioning_quality import CommissioningQuality, QualityCheck
from src.identification_quality import (
    MeasurementNoise, noise_information_fraction, scaled_geometry, split_difference,
)


@dataclass(frozen=True)
class MechanicalMeasurements:
    time_s: np.ndarray
    current_d_a: np.ndarray
    current_q_a: np.ndarray
    speed_rad_s: np.ndarray
    # None explicitly means unknown; it must never silently become zero.
    known_load_torque_nm: float | None
    noise: MeasurementNoise | None = None


@dataclass(frozen=True)
class MechanicalDiagnostics:
    rows: int
    effective_rank: int
    scaled_singular_values: np.ndarray
    scaled_condition_number: float
    column_norms: np.ndarray
    regressor_energy: np.ndarray
    conditional_column_norms: np.ndarray
    residual_rmse_nm_s: float
    target_rms_nm_s: float
    expected_sensor_residual_rms_nm_s: float | None
    noise_information_fraction: float | None
    sensor_covariance: np.ndarray | None
    electrical_sensitivity: np.ndarray
    electrical_standard_error_bound: np.ndarray | None
    standard_error_bound: np.ndarray | None
    component_snr: np.ndarray | None
    split_relative_difference: float | None


@dataclass(frozen=True)
class MechanicalEstimate:
    J: float
    B: float
    diagnostics: MechanicalDiagnostics
    window_time_s: np.ndarray
    torque_integral_nm_s: np.ndarray
    fitted_integral_nm_s: np.ndarray
    convergence_time_s: np.ndarray
    convergence_parameters: np.ndarray


def reconstruct_torque(data, electrical, flux, pole_pairs):
    """Te = 1.5 p [psi_f iq + (Ld - Lq) id iq]; no true torque input."""
    return 1.5 * pole_pairs * (
        flux.psi_f * data.current_q_a
        + (electrical.Ld - electrical.Lq) * data.current_d_a * data.current_q_a
    )


def estimate_mechanical_parameters(data, electrical, flux, pole_pairs, window_samples=50):
    """Fit integral(Te - known_load) = J delta(omega) + B integral(omega).

    Trapezoid integration uses sampled measurements; no pointwise derivative.
    Local sensor sensitivities retain shared endpoints. Electrical uncertainty
    uses a triangle-inequality SD bound, retaining unknown cross-stage correlation.
    """
    time = np.asarray(data.time_s)
    signals = (data.current_d_a, data.current_q_a, data.speed_rad_s)
    if time.ndim != 1 or len(time) < 3 or any(np.shape(s) != time.shape for s in signals):
        raise ValueError("mechanical.invalid_samples: matching one-dimensional arrays required")
    if any(not np.all(np.isfinite(s)) for s in (time, *signals)):
        raise ValueError("mechanical.invalid_samples: finite samples required")
    intervals = np.diff(time)
    if np.any(intervals <= 0) or not np.allclose(intervals, intervals[0], rtol=1e-9, atol=0):
        raise ValueError("mechanical.invalid_samples: uniform increasing sample times required")
    if data.known_load_torque_nm is None or not np.isfinite(data.known_load_torque_nm):
        raise ValueError("mechanical.unknown_load: explicitly known constant load required")
    if not isinstance(pole_pairs, int) or pole_pairs < 1:
        raise ValueError("mechanical.invalid_pole_pairs")
    if any(not np.isfinite(v) or v <= 0 for v in (electrical.Ld, electrical.Lq, flux.psi_f)):
        raise ValueError("mechanical.invalid_electrical_estimates")
    if not isinstance(window_samples, int) or window_samples < 2 or (len(time)-1)//window_samples < 4:
        raise ValueError("mechanical.insufficient_windows")

    width = window_samples
    starts = np.arange(0, len(time) - width, width)
    ends = starts + width
    weights = np.full(width + 1, intervals[0])
    weights[[0, -1]] *= 0.5
    delta = np.zeros(width + 1)
    delta[0], delta[-1] = -1, 1

    def integrate(signal):
        return np.array([weights @ signal[a:b+1] for a, b in zip(starts, ends)])

    torque = reconstruct_torque(data, electrical, flux, pole_pairs)
    matrix = np.column_stack((data.speed_rad_s[ends] - data.speed_rad_s[starts],
                              integrate(data.speed_rad_s)))
    target = integrate(torque - data.known_load_torque_nm)
    inverse, singular, norms, rank = scaled_geometry(matrix)
    if rank != 2:
        raise ValueError("mechanical.rank_deficiency")
    theta = inverse @ target
    if np.any(~np.isfinite(theta)) or np.any(theta <= 0):
        raise ValueError("mechanical.nonpositive_estimate")
    residual = target - matrix @ theta
    conditional_norms = np.array([
        np.linalg.norm(matrix[:, j] - matrix[:, 1-j] *
                       (matrix[:, 1-j] @ matrix[:, j]) / norms[1-j]**2)
        for j in range(2)
    ])
    c = 1.5 * pole_pairs
    # Electrical parameter order: [Ld, Lq, psi_f].
    target_electrical_jacobian = c * np.column_stack((
        integrate(data.current_d_a * data.current_q_a),
        -integrate(data.current_d_a * data.current_q_a), integrate(data.current_q_a),
    ))
    electrical_sensitivity = inverse @ target_electrical_jacobian
    sensor_covariance = expected_rms = fraction = electrical_bound = total_bound = snr = None
    if data.noise is not None:
        noise = data.noise
        js, jd, jq = (np.zeros((2, len(time))) for _ in range(3))
        normal_inverse = inverse @ inverse.T
        dx = np.stack((delta, weights))
        variances = []
        for k, (a, b) in enumerate(zip(starts, ends)):
            d_torque = c * (electrical.Ld - electrical.Lq) * data.current_q_a[a:b+1]
            q_torque = c * (flux.psi_f + (electrical.Ld - electrical.Lq) * data.current_d_a[a:b+1])
            js[:, a:b+1] += normal_inverse @ dx * residual[k] - inverse[:, k, None] * (theta @ dx)
            jd[:, a:b+1] += inverse[:, k, None] * (weights * d_torque)
            jq[:, a:b+1] += inverse[:, k, None] * (weights * q_torque)
            variances.append(noise.speed_std_rad_s**2 * np.sum((theta @ dx)**2)
                             + noise.current_std_a**2 * np.sum((weights*d_torque)**2 + (weights*q_torque)**2))
        sensor_covariance = (noise.speed_std_rad_s**2 * (js @ js.T)
                             + noise.current_std_a**2 * (jd @ jd.T + jq @ jq.T))
        expected_rms = float(np.sqrt(np.mean(variances)))
        fraction = noise_information_fraction(matrix, len(starts) * noise.speed_std_rad_s**2
                                               * np.array([2, intervals[0]**2 * (width - 0.5)]))
        if electrical.diagnostics is not None and flux.diagnostics is not None:
            e_se = electrical.diagnostics.parameter_standard_errors
            f_se = flux.diagnostics.parameter_standard_errors
            if e_se is not None and f_se is not None:
                # Flux and Ld/Lq errors are correlated; do not assume independence.
                electrical_bound = np.abs(electrical_sensitivity) @ np.array([e_se[1], e_se[2], f_se[0]])
                total_bound = np.sqrt(np.maximum(0, np.diag(sensor_covariance))) + electrical_bound
        contributions = np.abs(theta) * conditional_norms / np.sqrt(len(target))
        snr = contributions / max(expected_rms, np.finfo(float).tiny)
    diagnostics = MechanicalDiagnostics(
        len(target), rank, singular, float(singular[0]/singular[-1]), norms, norms**2,
        conditional_norms, float(np.sqrt(np.mean(residual**2))),
        float(np.sqrt(np.mean(target**2))), expected_rms, fraction, sensor_covariance,
        electrical_sensitivity, electrical_bound, total_bound, snr,
        split_difference(matrix, target, theta),
    )
    convergence, convergence_time = [], []
    for stop in range(4, len(target)+1):
        g, _, _, r = scaled_geometry(matrix[:stop])
        if r == 2:
            convergence.append(g @ target[:stop])
            convergence_time.append(time[ends[stop-1]])
    return MechanicalEstimate(float(theta[0]), float(theta[1]), diagnostics, time[ends],
                              target, matrix @ theta, np.asarray(convergence_time), np.asarray(convergence))


@dataclass(frozen=True)
class MechanicalQualityPolicy:
    """Pre-specified engineering budgets; no post-hoc error/performance inputs."""
    min_windows: int = 10
    max_scaled_condition: float = 100.0
    max_noise_information_fraction: float = 0.05
    max_relative_standard_error: float = 0.10 / 3
    max_split_relative_difference: float = 0.10
    min_component_snr: float = 3.0
    residual_noise_multiplier: float = 3.0
    relative_model_residual_allowance: float = 0.01

    def __post_init__(self):
        if any(not np.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError("Mechanical quality budgets must be positive and finite")


def assess_mechanical(estimate, policy=MechanicalQualityPolicy()):
    d = estimate.diagnostics
    checks = []

    def upper(name, value, limit):
        passed = value is not None and np.isfinite(value) and value <= limit
        checks.append(QualityCheck("mechanical." + name, value, limit, bool(passed)))

    upper("rank_deficiency", 2 - d.effective_rank, 0)
    upper("insufficient_windows", policy.min_windows - d.rows, 0)
    upper("conditioning", d.scaled_condition_number, policy.max_scaled_condition)
    upper("noise_information", d.noise_information_fraction, policy.max_noise_information_fraction)
    upper("relative_uncertainty", None if d.standard_error_bound is None else
          float(np.max(d.standard_error_bound / np.array([estimate.J, estimate.B]))),
          policy.max_relative_standard_error)
    upper("insufficient_excitation", None if d.component_snr is None else
          policy.min_component_snr - float(np.min(d.component_snr)), 0)
    upper("inconsistent_halves", d.split_relative_difference, policy.max_split_relative_difference)
    allowance = (None if d.expected_sensor_residual_rms_nm_s is None else
                 policy.residual_noise_multiplier * d.expected_sensor_residual_rms_nm_s
                 + policy.relative_model_residual_allowance * d.target_rms_nm_s)
    upper("excessive_residual", None if allowance is None or allowance <= 0 else
          d.residual_rmse_nm_s / allowance, 1.0)
    reasons = tuple(c.name for c in checks if not c.passed)
    return CommissioningQuality(not reasons, reasons, tuple(checks))
