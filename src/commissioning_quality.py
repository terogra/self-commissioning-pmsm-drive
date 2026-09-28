"""Acceptance policy using fitted diagnostics only; no physical plant inputs."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QualityPolicy:
    # Engineering budgets fixed before held-out evaluation; not probabilities.
    max_scaled_condition: float = 100.0
    max_noise_information_fraction: float = 0.05
    max_relative_standard_error: float = 0.10 / 3
    max_split_relative_difference: float = 0.10
    residual_noise_multiplier: float = 3.0
    relative_model_residual_allowance: float = 0.01
    max_back_emf_noise_ratio: float = 0.10
    min_windows: int = 10
    min_mechanical_speed_rad_s: float = 10.0

    def __post_init__(self):
        if any(not np.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError("Quality thresholds must be positive and finite")


@dataclass(frozen=True)
class QualityCheck:
    name: str
    value: float | None
    limit: float
    passed: bool


@dataclass(frozen=True)
class CommissioningQuality:
    accepted: bool
    rejection_reasons: tuple[str, ...]
    checks: tuple[QualityCheck, ...] = ()
    estimator_failure: str | None = None


def assess_commissioning(electrical, flux, pole_pairs, policy=QualityPolicy()):
    """Assess information, numerical reliability, sensor sensitivity, and fit.

    The estimates carry diagnostics computed from measurements and supplied
    sensor noise. Hidden physical parameters and tracking outcomes are not inputs.
    """
    checks = []
    reasons = []

    def upper(name, value, limit):
        passed = value is not None and np.isfinite(value) and value <= limit
        checks.append(QualityCheck(name, value, limit, bool(passed)))
        if not passed:
            reasons.append(name)

    for stage, estimate, names in (("standstill", electrical, ("Rs", "Ld", "Lq")),
                                    ("rotating", flux, ("psi_f",))):
        diag = None if estimate is None else estimate.diagnostics
        if diag is None:
            reasons.append(f"{stage}.missing_diagnostics")
            continue
        upper(f"{stage}.rank_deficiency", len(names) - diag.effective_rank, 0)
        windows = diag.rows // 2 if stage == "standstill" else diag.rows
        upper(f"{stage}.insufficient_windows", policy.min_windows - windows, 0)
        upper(f"{stage}.conditioning", diag.scaled_condition_number, policy.max_scaled_condition)
        upper(f"{stage}.noise_information", diag.noise_information_fraction,
              policy.max_noise_information_fraction)
        relative_se = None if diag.parameter_standard_errors is None else float(np.max(
            diag.parameter_standard_errors / np.abs([getattr(estimate, name) for name in names])
        ))
        upper(f"{stage}.relative_uncertainty", relative_se, policy.max_relative_standard_error)
        upper(f"{stage}.inconsistent_halves", diag.split_relative_difference,
              policy.max_split_relative_difference)
        allowance = (None if diag.expected_residual_rms_v_s is None else
                     policy.residual_noise_multiplier * diag.expected_residual_rms_v_s
                     + policy.relative_model_residual_allowance * diag.target_rms_v_s)
        residual_ratio = (None if allowance is None or allowance <= 0 else
                          diag.residual_rmse_v_s / allowance)
        upper(f"{stage}.excessive_residual", residual_ratio, 1.0)
        if stage == "rotating":
            speed_deficit = (None if diag.min_electrical_speed_rad_s is None else
                             pole_pairs * policy.min_mechanical_speed_rad_s - diag.min_electrical_speed_rad_s)
            upper("rotating.insufficient_speed", speed_deficit, 0)
            ratio = (None if diag.expected_residual_rms_v_s is None or diag.fitted_rms_v_s <= 0
                     else diag.expected_residual_rms_v_s / diag.fitted_rms_v_s)
            upper("rotating.weak_back_emf", ratio, policy.max_back_emf_noise_ratio)
    return CommissioningQuality(not reasons, tuple(reasons), tuple(checks))
