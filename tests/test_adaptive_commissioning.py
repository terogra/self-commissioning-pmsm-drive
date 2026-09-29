"""Process decisions are driven by measured diagnostics, with bounded retries."""

from dataclasses import asdict, replace

import pytest

from src.adaptive_commissioning import (
    DiagnosticSnapshot, RetryPolicy, Stage, SupervisorState, _mechanical_retry,
    _standstill_retry, run_adaptive_commissioning,
)
from src.commissioning import commission_from_measurements
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements


PLANT = PMSMParameters(Rs=.56, Ld=.0014, Lq=.0008, psi_f=.015, J=.0005, B=.0003)
PRIOR = PMSMParameters(Rs=.24, Ld=.0006, Lq=.0014, psi_f=.035, J=.0002, B=.0001)
STANDSTILL = ExcitationConfig(current_noise_std_a=.01, voltage_noise_std_v=.01,
                              speed_noise_std_rad_s=.02, seed=101)
ROTATING = RotatingExcitationConfig(q_voltage_base_v=5, current_noise_std_a=.01,
                                    voltage_noise_std_v=.01, speed_noise_std_rad_s=.02, seed=102)
MECHANICAL = MechanicalExcitationConfig(seed=103)


def run(standstill=STANDSTILL, rotating=ROTATING, mechanical=MECHANICAL, **kwargs):
    return run_adaptive_commissioning(
        lambda c: simulate_locked_rotor_measurements(PLANT, c),
        lambda c: simulate_driven_rotor_measurements(PLANT, c),
        lambda c, controller: simulate_mechanical_measurements(PLANT, controller, c).measurements,
        PRIOR, standstill_config=standstill, rotating_config=rotating,
        mechanical_config=mechanical, **kwargs,
    )


@pytest.fixture(scope="module")
def nominal():
    return run()


def test_nominal_accepts_and_retunes_without_retry(nominal):
    assert nominal.state == SupervisorState.FULL_ACCEPTED
    assert nominal.accepted and nominal.controller_parameters_updated
    assert nominal.attempt_counts == {"standstill": 1, "rotating": 1, "mechanical": 1}
    assert all(a.retry_decision == "accepted" for a in nominal.attempts)
    assert nominal.controller_parameters == nominal.full_commissioning.retuned_controller_parameters(PRIOR)
    assert nominal.controller_parameters.J != PRIOR.J


def test_weak_standstill_information_recovers_without_gate_change():
    weak = replace(STANDSTILL, d_voltage_v=.096, q_voltage_v=.112)
    result = run(standstill=weak)
    first, second = result.attempts[:2]
    assert first.quality.rejection_reasons == ("standstill.noise_information",)
    assert first.retry_action == "increase_standstill_voltage"
    assert second.quality.accepted and result.accepted
    assert first.quality.checks[3].limit == second.quality.checks[3].limit
    assert first.config == weak and first.next_config == second.config


def test_known_zero_standstill_input_has_one_bounded_recovery():
    zero = replace(STANDSTILL, d_voltage_v=0, q_voltage_v=0)
    result = run(standstill=zero)
    assert result.accepted
    assert result.attempt_counts["standstill"] == 2
    assert result.attempts[0].retry_action == "add_standstill_excitation"
    assert result.attempts[0].quality.estimator_failure is not None


def test_weak_flux_information_selects_speed_retry():
    weak = replace(ROTATING, speed_rpm=120, current_noise_std_a=.1,
                   voltage_noise_std_v=.1, speed_noise_std_rad_s=.5)
    result = run(rotating=weak)
    attempts = [a for a in result.attempts if a.stage == Stage.ROTATING]
    assert len(attempts) == 2 and result.accepted
    assert "rotating.weak_back_emf" in attempts[0].quality.rejection_reasons
    assert attempts[0].retry_action == "increase_rotating_speed"
    assert attempts[1].config.speed_rpm > weak.speed_rpm


def test_weak_mechanical_information_retains_failed_attempts_and_recovers():
    weak = replace(MECHANICAL, iq_plateaus_a=tuple(.08*v for v in MECHANICAL.iq_plateaus_a))
    result = run(mechanical=weak)
    attempts = [a for a in result.attempts if a.stage == Stage.MECHANICAL]
    assert result.accepted and len(attempts) == 3
    assert attempts[0].retry_action == "extend_mechanical_plateaus_for_B"
    assert attempts[1].retry_action == "increase_mechanical_plateaus_for_J"
    assert attempts[0].diagnostics.component_snr[1] < attempts[0].diagnostics.component_snr[0]
    assert attempts[-1].quality.accepted


def test_mechanical_J_and_B_select_different_actions():
    j_weak = DiagnosticSnapshot(component_snr=(1.0, 10.0), relative_sensitivity=(.2, .01))
    b_weak = DiagnosticSnapshot(component_snr=(10.0, 1.0), relative_sensitivity=(.01, .2))
    reasons = ("mechanical.insufficient_excitation",)
    _, j_action = _mechanical_retry(replace(MECHANICAL, iq_plateaus_a=tuple(.5*v for v in MECHANICAL.iq_plateaus_a)),
                                    reasons, j_weak, RetryPolicy())
    _, b_action = _mechanical_retry(MECHANICAL, reasons, b_weak, RetryPolicy())
    assert j_action == "increase_mechanical_plateaus_for_J"
    assert b_action == "extend_mechanical_plateaus_for_B"


def test_operating_infeasibility_does_not_retry_or_reject_identification(nominal):
    request = OperatingPointRequest(2000, .05, 12, 5)
    result = run(operating_request=request)
    assert result.state == SupervisorState.OPERATING_INFEASIBLE
    assert result.accepted and result.controller_parameters_updated
    assert result.operating_feasibility.reasons == ("operating.voltage_limit",)
    assert result.attempt_counts == nominal.attempt_counts
    assert result.full_commissioning.quality.accepted
    assert not hasattr(result, "closed_loop_dynamic_success")


def test_retry_budget_is_explicit_and_rejection_keeps_prior():
    weak = replace(STANDSTILL, d_voltage_v=.096, q_voltage_v=.112)
    policy = RetryPolicy(max_electrical_attempts=1)
    result = run(standstill=weak, retry_policy=policy)
    assert result.state == SupervisorState.RETRY_BUDGET_EXHAUSTED
    assert result.terminal_reason == "standstill.retry_budget_exhausted"
    assert result.attempt_counts["standstill"] == 1
    assert result.attempts[0].retry_decision == "budget_exhausted"
    assert result.controller_parameters is PRIOR and not result.controller_parameters_updated


def test_persistent_residual_is_nonretryable():
    config, reason = _standstill_retry(STANDSTILL, ("standstill.excessive_residual",), RetryPolicy())
    assert config is None and reason == "model_residual_terminal"
    config, reason = _mechanical_retry(MECHANICAL, ("mechanical.excessive_residual",), None, RetryPolicy())
    assert config is None and reason == "model_residual_terminal"


def test_retry_bounds_and_initial_design_limits():
    with pytest.raises(ValueError, match="invalid_retry_policy"):
        RetryPolicy(max_electrical_attempts=0)
    with pytest.raises(ValueError, match="initial_configuration_exceeds_design_limit"):
        run(standstill=replace(STANDSTILL, d_voltage_v=4))
    with pytest.raises(ValueError, match="initial_configuration_exceeds_design_limit"):
        run(mechanical=replace(MECHANICAL, current_reference_limit_a=2))
    with pytest.raises(ValueError, match="initial_configuration_exceeds_design_limit"):
        run(rotating=replace(ROTATING, speed_rpm=-1500))


def test_retry_sequence_is_deterministic_and_one_shot_api_still_works():
    weak = replace(STANDSTILL, d_voltage_v=.096, q_voltage_v=.112)
    a, b = run(standstill=weak), run(standstill=weak)
    assert [(v.stage, v.quality.rejection_reasons, v.retry_action, v.config)
            for v in a.attempts] == [(v.stage, v.quality.rejection_reasons, v.retry_action, v.config)
                                   for v in b.attempts]
    assert a.controller_parameters == b.controller_parameters
    one_shot = commission_from_measurements(
        simulate_locked_rotor_measurements(PLANT, STANDSTILL),
        simulate_driven_rotor_measurements(PLANT, ROTATING), PRIOR.pole_pairs)
    assert one_shot.quality.accepted


def test_quality_policies_are_frozen_and_truth_labels_are_not_inputs():
    from inspect import signature
    from src.commissioning_quality import QualityPolicy
    from src.mechanical_identification import MechanicalQualityPolicy
    e, m = QualityPolicy(), MechanicalQualityPolicy()
    before = asdict(e), asdict(m)
    result = run(electrical_quality_policy=e, mechanical_quality_policy=m)
    assert (asdict(e), asdict(m)) == before
    names = set(signature(run_adaptive_commissioning).parameters)
    assert not names.intersection({"plant", "true_parameters", "parameter_errors", "control_outcome"})
    assert result.accepted


def test_population_design_is_deterministic_and_truth_is_posthoc():
    from experiments.adaptive_commissioning import generate_cases, run_case
    first, again = generate_cases("development"), generate_cases("development")
    held_out = generate_cases("evaluation")
    assert [asdict(c) for c in first] == [asdict(c) for c in again]
    assert first[0].plant != held_out[0].plant
    assert len(first) == len(held_out) == 9
    case = next(c for c in first if c.name == "weak_electrical")
    rows, history, truth = run_case(case)
    assert len(rows) == 2 and rows[0]["method"] == "one_shot"
    assert not rows[0]["full_accepted"] and rows[1]["full_accepted"]
    assert history[0]["configuration"] == asdict(case.standstill)
    assert "Rs" in truth and "Rs" not in history[0]
    assert all("true_" not in key for attempt in history for key in attempt)
