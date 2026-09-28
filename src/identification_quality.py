"""Measured-data diagnostics for integrated least squares.

Sensor-noise propagation is a local sensitivity calculation, not a confidence
interval: it does not include errors-in-variables bias or unmodeled physics.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MeasurementNoise:
    """Known/calibrated per-sample standard deviations in the measured dq frame.

    Assumes independent, zero-mean samples and independent sensor channels.
    """
    current_std_a: float = 0.0
    voltage_std_v: float = 0.0
    speed_std_rad_s: float = 0.0

    def __post_init__(self):
        if any(not np.isfinite(v) or v < 0 for v in (
            self.current_std_a, self.voltage_std_v, self.speed_std_rad_s
        )):
            raise ValueError("Sensor standard deviations must be finite and nonnegative")


@dataclass(frozen=True)
class RegressionDiagnostics:
    parameter_names: tuple[str, ...]
    rows: int
    effective_rank: int
    scaled_singular_values: np.ndarray
    scaled_condition_number: float
    column_norms: np.ndarray
    regressor_energy: np.ndarray
    residual_rmse_v_s: float
    target_rms_v_s: float
    fitted_rms_v_s: float
    noise_information_fraction: float | None
    expected_residual_rms_v_s: float | None
    parameter_covariance: np.ndarray | None
    parameter_standard_errors: np.ndarray | None
    split_relative_difference: float | None
    min_electrical_speed_rad_s: float | None = None


def scaled_geometry(matrix):
    """Return physical pseudoinverse, scaled SVD, and column norms.

    X = Z D, so X+ = D^-1 Z+; this same map must be used for covariance.
    """
    norms = np.linalg.norm(matrix, axis=0)
    safe_norms = np.where(norms > 0, norms, 1.0)
    scaled = matrix / safe_norms
    singular = np.linalg.svd(scaled, compute_uv=False)
    rank = int(np.linalg.matrix_rank(scaled))
    inverse = np.linalg.pinv(scaled) / safe_norms[:, None]
    return inverse, singular, norms, rank


def noise_information_fraction(matrix, noise_column_energy):
    """Largest noise/observed-information ratio in any parameter direction.

    Expected X-noise normal matrix is diagonal for these symmetric window
    integrals. Work in column-scaled coordinates so the ratio is unit invariant.
    This is an errors-in-variables warning, not a bound on actual parameter error.
    """
    norms = np.linalg.norm(matrix, axis=0)
    scaled_inverse = np.linalg.pinv(matrix / norms)
    noise_root = np.diag(np.sqrt(noise_column_energy) / norms)
    ratios = noise_root @ (scaled_inverse @ scaled_inverse.T) @ noise_root
    return float(max(0.0, np.linalg.eigvalsh(ratios)[-1]))


def split_difference(matrix, target, coefficients, rows_per_window=1):
    """Compare fits on first/second temporal halves to the full-record fit."""
    half = (len(target) // (2 * rows_per_window)) * rows_per_window
    fits = []
    for x, y in ((matrix[:half], target[:half]), (matrix[half:], target[half:])):
        inverse, _, _, rank = scaled_geometry(x)
        if rank != matrix.shape[1]:
            return None
        fits.append(inverse @ y)
    return float(np.max(np.abs(fits[0] - fits[1]) / np.abs(coefficients)))


def standstill_diagnostics(data, matrix, target, coefficients, starts, ends):
    inverse, singular, norms, rank = scaled_geometry(matrix)
    residual = target - matrix @ coefficients
    dt = data.time_s[1] - data.time_s[0]
    width = int(ends[0] - starts[0])
    covariance = noise_fraction = expected_rms = None
    if data.noise is not None:
        noise = data.noise
        weights = np.ones(width + 1) * dt
        weights[[0, -1]] *= 0.5
        delta = np.zeros(width + 1)
        delta[0], delta[-1] = -1.0, 1.0
        # Exact local derivative of OLS: dtheta = (X'X)^-1 dX' r
        # + X+ (dy - dX theta). Accumulating shared endpoints preserves covariance.
        inverse_normal = inverse @ inverse.T
        covariance = np.zeros((3, 3))
        residual_variances = []
        for axis, inductance_column in ((0, 1), (1, 2)):
            current_jacobian = np.zeros((3, len(data.time_s)))
            voltage_jacobian = np.zeros((3, len(data.time_s) - 1))
            dx = np.zeros((3, width + 1))
            dx[0] = weights
            dx[inductance_column] = delta
            for window, (a, b) in enumerate(zip(starts, ends)):
                row = 2 * window + axis
                current_jacobian[:, a:b + 1] += (
                    inverse_normal @ dx * residual[row]
                    - inverse[:, row, None] * (coefficients @ dx)[None, :]
                )
                voltage_jacobian[:, a:b] += inverse[:, row, None] * dt
            covariance += noise.current_std_a**2 * (current_jacobian @ current_jacobian.T)
            covariance += noise.voltage_std_v**2 * (voltage_jacobian @ voltage_jacobian.T)
            residual_variances.append(
                noise.current_std_a**2 * np.sum((coefficients @ dx)**2)
                + noise.voltage_std_v**2 * width * dt**2
            )
        noise_energy = noise.current_std_a**2 * len(starts) * np.array([
            2 * dt**2 * (width - 0.5), 2.0, 2.0
        ])
        noise_fraction = noise_information_fraction(matrix, noise_energy)
        expected_rms = float(np.sqrt(np.mean(residual_variances)))
    return RegressionDiagnostics(
        parameter_names=("Rs", "Ld", "Lq"), rows=len(target),
        effective_rank=rank, scaled_singular_values=singular,
        scaled_condition_number=float(singular[0] / singular[-1]),
        column_norms=norms, regressor_energy=norms**2,
        residual_rmse_v_s=float(np.sqrt(np.mean(residual**2))),
        target_rms_v_s=float(np.sqrt(np.mean(target**2))),
        fitted_rms_v_s=float(np.sqrt(np.mean((matrix @ coefficients)**2))),
        noise_information_fraction=noise_fraction,
        expected_residual_rms_v_s=expected_rms,
        parameter_covariance=covariance,
        parameter_standard_errors=None if covariance is None else np.sqrt(np.maximum(0, np.diag(covariance))),
        split_relative_difference=split_difference(matrix, target, coefficients, rows_per_window=2),
    )


def flux_diagnostics(data, electrical, pole_pairs, psi_f, x, y, starts, ends,
                     q_area, cross_area):
    matrix = x[:, None]
    _, singular, norms, rank = scaled_geometry(matrix)
    residual = y - x * psi_f
    dt = data.time_s[1] - data.time_s[0]
    width = int(ends[0] - starts[0])
    covariance = noise_fraction = expected_rms = None
    prior = electrical.diagnostics
    if data.noise is not None and prior is not None and prior.parameter_covariance is not None:
        noise = data.noise
        energy = float(x @ x)
        dy = x / energy
        dx = (y - 2 * x * psi_f) / energy
        weights = np.ones(width + 1) * dt
        weights[[0, -1]] *= 0.5
        delta = np.zeros(width + 1)
        delta[0], delta[-1] = -1.0, 1.0
        jq = np.zeros(len(data.time_s))
        jd = np.zeros_like(jq)
        js = np.zeros_like(jq)
        jv = np.zeros(len(data.time_s) - 1)
        residual_variances = []
        for k, (a, b) in enumerate(zip(starts, ends)):
            omega_e = pole_pairs * data.speed_rad_s[a:b + 1]
            q_weights = -electrical.Rs * weights - electrical.Lq * delta
            d_weights = -electrical.Ld * omega_e * weights
            speed_weights = -pole_pairs * (electrical.Ld * data.current_d_a[a:b + 1] + psi_f) * weights
            jq[a:b + 1] += dy[k] * q_weights
            jd[a:b + 1] += dy[k] * d_weights
            js[a:b + 1] += (dx[k] - dy[k] * electrical.Ld * data.current_d_a[a:b + 1]) * pole_pairs * weights
            jv[a:b] += dy[k] * dt
            residual_variances.append(
                noise.current_std_a**2 * (q_weights @ q_weights + d_weights @ d_weights)
                + noise.speed_std_rad_s**2 * (speed_weights @ speed_weights)
                + noise.voltage_std_v**2 * width * dt**2
            )
        gradient = -np.array([
            x @ q_area, x @ cross_area,
            x @ (data.current_q_a[ends] - data.current_q_a[starts]),
        ]) / energy
        variance = (noise.current_std_a**2 * (jq @ jq + jd @ jd)
                    + noise.voltage_std_v**2 * (jv @ jv)
                    + noise.speed_std_rad_s**2 * (js @ js)
                    + gradient @ prior.parameter_covariance @ gradient)
        covariance = np.array([[float(max(0.0, variance))]])
        noise_energy = len(x) * (pole_pairs * noise.speed_std_rad_s * dt)**2 * (width - 0.5)
        noise_fraction = float(noise_energy / energy)
        expected_rms = float(np.sqrt(np.mean(residual_variances)))
    return RegressionDiagnostics(
        parameter_names=("psi_f",), rows=len(y), effective_rank=rank,
        scaled_singular_values=singular, scaled_condition_number=1.0,
        column_norms=norms, regressor_energy=norms**2,
        residual_rmse_v_s=float(np.sqrt(np.mean(residual**2))),
        target_rms_v_s=float(np.sqrt(np.mean(y**2))),
        fitted_rms_v_s=float(np.sqrt(np.mean((x * psi_f)**2))),
        noise_information_fraction=noise_fraction, expected_residual_rms_v_s=expected_rms,
        parameter_covariance=covariance,
        parameter_standard_errors=None if covariance is None else np.sqrt(np.diag(covariance)),
        split_relative_difference=split_difference(matrix, y, np.array([psi_f])),
        min_electrical_speed_rad_s=float(np.min(np.abs(pole_pairs * data.speed_rad_s))),
    )
