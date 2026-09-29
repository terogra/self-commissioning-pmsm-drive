"""Bounded commissioning process supervisor; decisions use measurements only.

Measurement providers are the simulation/hardware boundary. This module never
receives a plant, true parameter, hidden torque, or closed-loop outcome.
"""

from dataclasses import dataclass, replace
from enum import Enum
from math import copysign, hypot, isfinite, sqrt
from typing import Callable

import numpy as np

from src.commissioning import CommissioningResult
from src.commissioning_quality import CommissioningQuality, QualityPolicy, assess_commissioning
from src.full_commissioning import FullCommissioningResult, MechanicalCommissioningResult, complete_commissioning
from src.identification import ExcitationConfig, estimate_standstill_parameters
from src.mechanical_excitation import MechanicalExcitationConfig
from src.mechanical_identification import MechanicalQualityPolicy
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.rotating_identification import RotatingExcitationConfig, estimate_flux_linkage


class SupervisorState(str, Enum):
    FULL_ACCEPTED = "full_accepted"
    OPERATING_FEASIBLE = "operating_feasible"
    OPERATING_INFEASIBLE = "operating_infeasible"
    TERMINAL_REJECTED = "terminal_rejected"
    RETRY_BUDGET_EXHAUSTED = "retry_budget_exhausted"


class Stage(str, Enum):
    STANDSTILL = "standstill"
    ROTATING = "rotating"
    MECHANICAL = "mechanical"


@dataclass(frozen=True)
class RetryPolicy:
    """Simulation/design bounds; none is a hardware safety certification."""

    max_electrical_attempts: int = 4  # separately for standstill and rotating
    max_mechanical_attempts: int = 4
    max_standstill_voltage_magnitude_v: float = 3.0
    max_standstill_duration_s: float = 0.8
    max_rotating_speed_rpm: float = 1200.0
    max_rotating_duration_s: float = 0.6
    max_mechanical_reference_a: float = 1.0
    max_mechanical_plateau_duration_s: float = 0.5
    excitation_multiplier: float = 2.0
    duration_multiplier: float = 2.0
    speed_multiplier: float = 2.0

    def __post_init__(self):
        if (any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in
                (self.max_electrical_attempts, self.max_mechanical_attempts))
                or any(not isfinite(v) or v <= 0 for v in (
                    self.max_standstill_voltage_magnitude_v, self.max_standstill_duration_s,
                    self.max_rotating_speed_rpm, self.max_rotating_duration_s,
                    self.max_mechanical_reference_a, self.max_mechanical_plateau_duration_s))
                or any(not isfinite(v) or v <= 1 for v in (
                    self.excitation_multiplier, self.duration_multiplier, self.speed_multiplier))):
            raise ValueError("supervisor.invalid_retry_policy")


@dataclass(frozen=True)
class DiagnosticSnapshot:
    effective_rank: int | None = None
    scaled_condition_number: float | None = None
    noise_information_fraction: float | None = None
    split_relative_difference: float | None = None
    residual_rmse: float | None = None
    relative_sensitivity: tuple[float, ...] | None = None
    component_snr: tuple[float, ...] | None = None


@dataclass(frozen=True)
class AttemptRecord:
    stage: Stage
    number: int
    config: ExcitationConfig | RotatingExcitationConfig | MechanicalExcitationConfig
    estimator_succeeded: bool
    estimate: object | None
    quality: CommissioningQuality
    diagnostics: DiagnosticSnapshot | None
    retry_decision: str  # accepted, retry, terminal, budget_exhausted
    retry_action: str | None
    next_config: ExcitationConfig | RotatingExcitationConfig | MechanicalExcitationConfig | None


@dataclass(frozen=True)
class SupervisorResult:
    state: SupervisorState
    full_commissioning: FullCommissioningResult | None
    operating_feasibility: object | None
    attempts: tuple[AttemptRecord, ...]
    terminal_reason: str | None
    controller_parameters_updated: bool
    controller_parameters: object

    @property
    def accepted(self):
        return self.full_commissioning is not None and self.full_commissioning.quality.accepted

    @property
    def attempt_counts(self):
        return {stage.value: sum(a.stage == stage for a in self.attempts) for stage in Stage}


def _snapshot(estimate, stage):
    if estimate is None or estimate.diagnostics is None:
        return None
    d = estimate.diagnostics
    if stage == Stage.MECHANICAL:
        sensitivity = d.standard_error_bound
        parameters = (estimate.J, estimate.B)
        residual = d.residual_rmse_nm_s
        snr = d.component_snr
    else:
        sensitivity = d.parameter_standard_errors
        parameters = ((estimate.Rs, estimate.Ld, estimate.Lq) if stage == Stage.STANDSTILL
                      else (estimate.psi_f,))
        residual = d.residual_rmse_v_s
        snr = None
    relative = None if sensitivity is None else tuple(float(v) for v in sensitivity / np.abs(parameters))
    return DiagnosticSnapshot(d.effective_rank, float(d.scaled_condition_number),
        None if d.noise_information_fraction is None else float(d.noise_information_fraction),
        None if d.split_relative_difference is None else float(d.split_relative_difference),
        float(residual), relative, None if snr is None else tuple(float(v) for v in snr))


def _standstill_quality(electrical, pole_pairs, policy):
    # Reuse the unchanged full electrical gate, selecting its standstill checks.
    full = assess_commissioning(electrical, None, pole_pairs, policy)
    checks = tuple(c for c in full.checks if c.name.startswith("standstill."))
    reasons = tuple(c.name for c in checks if not c.passed)
    return CommissioningQuality(not reasons, reasons, checks)


def _estimator_failure(stage, exc):
    message = str(exc)
    if stage == Stage.STANDSTILL and message == "Excitation does not identify all three parameters":
        reason = "standstill.rank_deficiency"
    elif stage == Stage.MECHANICAL and message.startswith("mechanical.rank_deficiency"):
        reason = "mechanical.rank_deficiency"
    elif stage == Stage.ROTATING and message == "Flux linkage requires sustained nonzero measured speed":
        reason = "rotating.insufficient_speed"
    else:
        reason = f"{stage.value}.estimator_failure: {message}"
    return CommissioningQuality(False, (reason,), estimator_failure=message)


def _standstill_retry(config, reasons, policy):
    if "standstill.excessive_residual" in reasons:
        return None, "model_residual_terminal"
    magnitude = hypot(config.d_voltage_v, config.q_voltage_v)
    zero_input_failure = (magnitude == 0 and reasons == (
        "standstill.estimator_failure: Electrical estimates must be positive",))
    if zero_input_failure:
        target = min(policy.max_standstill_voltage_magnitude_v,
                     config.dc_bus_voltage_v / sqrt(3), 0.2)
        return replace(config, d_voltage_v=target * 0.65, q_voltage_v=target * 0.75,
                       seed=config.seed + 1), "add_standstill_excitation"
    allowed = {"standstill.rank_deficiency", "standstill.insufficient_windows",
               "standstill.conditioning", "standstill.noise_information",
               "standstill.relative_uncertainty", "standstill.inconsistent_halves"}
    if not reasons or set(reasons) - allowed:
        return None, "unsupported_diagnostic"
    if "standstill.insufficient_windows" in reasons or "standstill.inconsistent_halves" in reasons:
        duration = min(policy.max_standstill_duration_s, config.duration_s * policy.duration_multiplier)
        if duration > config.duration_s:
            return replace(config, duration_s=duration, seed=config.seed + 1), "extend_standstill_record"
    if "standstill.conditioning" in reasons:
        d_hold = max(3, config.d_hold_samples // 2)
        q_hold = max(4, config.q_hold_samples // 2)
        if d_hold == q_hold:
            q_hold += 1
        if (d_hold, q_hold) != (config.d_hold_samples, config.q_hold_samples):
            return replace(config, d_hold_samples=d_hold, q_hold_samples=q_hold,
                           seed=config.seed + 1), "enrich_standstill_switching"
    target = min(policy.max_standstill_voltage_magnitude_v, config.dc_bus_voltage_v / sqrt(3),
                 max(magnitude * policy.excitation_multiplier, 0.2))
    if target > magnitude and magnitude == 0:
        return replace(config, d_voltage_v=target * 0.65, q_voltage_v=target * 0.75,
                       seed=config.seed + 1), "add_standstill_excitation"
    if target > magnitude:
        factor = target / magnitude
        return replace(config, d_voltage_v=config.d_voltage_v * factor,
                       q_voltage_v=config.q_voltage_v * factor, seed=config.seed + 1), "increase_standstill_voltage"
    duration = min(policy.max_standstill_duration_s, config.duration_s * policy.duration_multiplier)
    if duration > config.duration_s:
        return replace(config, duration_s=duration, seed=config.seed + 1), "extend_standstill_record"
    return None, "standstill_design_limit"


def _rotating_retry(config, reasons, policy):
    if "rotating.excessive_residual" in reasons:
        return None, "model_residual_terminal"
    allowed = {"rotating.rank_deficiency", "rotating.insufficient_windows", "rotating.conditioning",
               "rotating.noise_information", "rotating.relative_uncertainty",
               "rotating.inconsistent_halves", "rotating.insufficient_speed", "rotating.weak_back_emf"}
    if not reasons or set(reasons) - allowed:
        return None, "unsupported_diagnostic"
    if "rotating.insufficient_windows" in reasons or "rotating.inconsistent_halves" in reasons:
        duration = min(policy.max_rotating_duration_s, config.duration_s * policy.duration_multiplier)
        if duration > config.duration_s:
            return replace(config, duration_s=duration, seed=config.seed + 1), "extend_rotating_record"
    speed = copysign(min(policy.max_rotating_speed_rpm,
                        abs(config.speed_rpm) * policy.speed_multiplier), config.speed_rpm)
    if abs(speed) > abs(config.speed_rpm):
        return replace(config, speed_rpm=speed, seed=config.seed + 1), "increase_rotating_speed"
    duration = min(policy.max_rotating_duration_s, config.duration_s * policy.duration_multiplier)
    if duration > config.duration_s:
        return replace(config, duration_s=duration, seed=config.seed + 1), "extend_rotating_record"
    return None, "rotating_design_limit"


def _mechanical_retry(config, reasons, snapshot, policy):
    if "mechanical.excessive_residual" in reasons:
        return None, "model_residual_terminal"
    allowed = {"mechanical.rank_deficiency", "mechanical.insufficient_windows",
               "mechanical.conditioning", "mechanical.noise_information",
               "mechanical.relative_uncertainty", "mechanical.insufficient_excitation",
               "mechanical.inconsistent_halves"}
    if not reasons or set(reasons) - allowed:
        return None, "unsupported_diagnostic"
    weak_b = (snapshot is not None and snapshot.component_snr is not None
              and snapshot.component_snr[1] < snapshot.component_snr[0])
    if snapshot is not None and snapshot.relative_sensitivity is not None:
        weak_b = weak_b or snapshot.relative_sensitivity[1] > snapshot.relative_sensitivity[0]
    duration_first = (weak_b or "mechanical.insufficient_windows" in reasons
                      or "mechanical.inconsistent_halves" in reasons
                      or "mechanical.conditioning" in reasons)
    duration = min(policy.max_mechanical_plateau_duration_s,
                   config.plateau_duration_s * policy.duration_multiplier)
    if duration_first and duration > config.plateau_duration_s:
        return replace(config, plateau_duration_s=duration, seed=config.seed + 1), "extend_mechanical_plateaus_for_B"
    magnitude = max(abs(v) for v in config.iq_plateaus_a)
    target = min(policy.max_mechanical_reference_a,
                 max(magnitude * policy.excitation_multiplier, 0.1))
    if target > magnitude and magnitude == 0:
        pattern = (0.8, 0.0, 0.4, -0.4, 0.0) * 2
        return replace(config, iq_plateaus_a=tuple(v * target for v in pattern),
                       current_reference_limit_a=max(config.current_reference_limit_a, 0.8 * target),
                       seed=config.seed + 1), "add_mechanical_plateaus_for_J"
    if target > magnitude:
        factor = target / magnitude
        return replace(config, iq_plateaus_a=tuple(v * factor for v in config.iq_plateaus_a),
                       current_reference_limit_a=max(config.current_reference_limit_a, target),
                       seed=config.seed + 1), "increase_mechanical_plateaus_for_J"
    if duration > config.plateau_duration_s:
        return replace(config, plateau_duration_s=duration, seed=config.seed + 1), "extend_mechanical_plateaus_for_B"
    return None, "mechanical_design_limit"


def _validate_initial(standstill, rotating, mechanical, policy):
    if (not mechanical.iq_plateaus_a
            or hypot(standstill.d_voltage_v, standstill.q_voltage_v) > policy.max_standstill_voltage_magnitude_v
            or standstill.duration_s > policy.max_standstill_duration_s
            or abs(rotating.speed_rpm) > policy.max_rotating_speed_rpm
            or rotating.duration_s > policy.max_rotating_duration_s
            or max(abs(v) for v in mechanical.iq_plateaus_a) > policy.max_mechanical_reference_a
            or mechanical.current_reference_limit_a > policy.max_mechanical_reference_a
            or mechanical.plateau_duration_s > policy.max_mechanical_plateau_duration_s):
        raise ValueError("supervisor.initial_configuration_exceeds_design_limit")


def run_adaptive_commissioning(
    standstill_measurements: Callable[[ExcitationConfig], object],
    rotating_measurements: Callable[[RotatingExcitationConfig], object],
    mechanical_measurements: Callable[[MechanicalExcitationConfig, object], object],
    prior_controller_parameters,
    *,
    standstill_config: ExcitationConfig = ExcitationConfig(),
    rotating_config: RotatingExcitationConfig = RotatingExcitationConfig(),
    mechanical_config: MechanicalExcitationConfig = MechanicalExcitationConfig(),
    retry_policy: RetryPolicy = RetryPolicy(),
    electrical_quality_policy: QualityPolicy = QualityPolicy(),
    mechanical_quality_policy: MechanicalQualityPolicy = MechanicalQualityPolicy(),
    operating_request: OperatingPointRequest | None = None,
) -> SupervisorResult:
    """Run the stages with frozen gates and bounded, diagnosis-led retries.

    Providers return sampled measurement records. They alone may hold a plant.
    No controller parameters are updated until *both* quality gates accept.
    """
    _validate_initial(standstill_config, rotating_config, mechanical_config, retry_policy)
    pole_pairs = prior_controller_parameters.pole_pairs
    history = []
    electrical = flux = None
    electrical_result = None
    full = None

    def terminal(state, reason):
        return SupervisorResult(state, full, None, tuple(history), reason, False,
                                prior_controller_parameters)

    for stage, initial, limit in (
        (Stage.STANDSTILL, standstill_config, retry_policy.max_electrical_attempts),
        (Stage.ROTATING, rotating_config, retry_policy.max_electrical_attempts),
        (Stage.MECHANICAL, mechanical_config, retry_policy.max_mechanical_attempts),
    ):
        config = initial
        for number in range(1, limit + 1):
            estimate = None
            try:
                if stage == Stage.STANDSTILL:
                    estimate = estimate_standstill_parameters(standstill_measurements(config))
                    quality = _standstill_quality(estimate, pole_pairs, electrical_quality_policy)
                elif stage == Stage.ROTATING:
                    estimate = estimate_flux_linkage(rotating_measurements(config), electrical, pole_pairs)
                    quality = assess_commissioning(electrical, estimate, pole_pairs, electrical_quality_policy)
                else:
                    data = mechanical_measurements(config, electrical_result.retuned_controller_parameters(
                        prior_controller_parameters))
                    full_attempt = complete_commissioning(electrical_result, data, mechanical_quality_policy)
                    estimate = full_attempt.mechanical.estimate
                    quality = full_attempt.mechanical.quality
                    full = full_attempt
            except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
                quality = _estimator_failure(stage, exc)
            snapshot = _snapshot(estimate, stage)
            if quality.accepted:
                history.append(AttemptRecord(stage, number, config, True, estimate, quality, snapshot,
                                             "accepted", None, None))
                if stage == Stage.STANDSTILL:
                    electrical = estimate
                elif stage == Stage.ROTATING:
                    flux = estimate
                    electrical_result = CommissioningResult(electrical, flux, pole_pairs, quality)
                break
            if stage == Stage.STANDSTILL:
                next_config, action = _standstill_retry(config, quality.rejection_reasons, retry_policy)
            elif stage == Stage.ROTATING:
                next_config, action = _rotating_retry(config, quality.rejection_reasons, retry_policy)
            else:
                next_config, action = _mechanical_retry(config, quality.rejection_reasons, snapshot, retry_policy)
            retryable = next_config is not None
            exhausted = retryable and number == limit
            decision = "budget_exhausted" if exhausted else "retry" if retryable else "terminal"
            history.append(AttemptRecord(stage, number, config, estimate is not None, estimate, quality,
                                         snapshot, decision, action, next_config if decision == "retry" else None))
            if exhausted:
                return terminal(SupervisorState.RETRY_BUDGET_EXHAUSTED, f"{stage.value}.retry_budget_exhausted")
            if not retryable:
                return terminal(SupervisorState.TERMINAL_REJECTED, f"{stage.value}.{action}")
            config = next_config
    assert full is not None and full.quality.accepted
    controller = full.retuned_controller_parameters(prior_controller_parameters)
    operating = None if operating_request is None else assess_operating_point(full, operating_request)
    state = (SupervisorState.FULL_ACCEPTED if operating is None else
             SupervisorState.OPERATING_FEASIBLE if operating.steady_state_feasible else
             SupervisorState.OPERATING_INFEASIBLE)
    return SupervisorResult(state, full, operating, tuple(history), None, True, controller)
