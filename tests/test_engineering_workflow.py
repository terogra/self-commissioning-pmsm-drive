"""Headless integration tests against the real, unchanged M1-M18 backend."""

from dataclasses import asdict, replace

import numpy as np
import pytest

from src.commissioning import CommissioningRejectedError
from src.dynamic_feasibility import DynamicAnalysisConfig, DynamicOperatingRequest, assess_dynamic_operating_point
from src.engineering_workflow import EngineeringWorkflowConfig, export_firmware_configuration, run_engineering_workflow
from src.firmware_config import build_firmware_config, export_c_header
from src.foc import CurrentFOCController
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.speed_control import SpeedController
from src.speed_foc_simulation import run_speed_foc_simulation
from src.version import __version__


@pytest.fixture(scope="module")
def nominal():
    return run_engineering_workflow()


@pytest.fixture(scope="module")
def rejected():
    return run_engineering_workflow(EngineeringWorkflowConfig(scenario="timing_one_sample"))


def test_nominal_real_pipeline_reaches_all_stages(nominal):
    assert nominal.status == "FULL ACCEPTED"
    assert nominal.firmware_available
    assert nominal.steady_feasibility is not None and nominal.dynamic_feasibility is not None
    assert nominal.control.metrics["operation_status"] == "evaluated"
    assert nominal.control.metrics["control_success"]
    assert [a.stage.value for a in nominal.attempts] == ["standstill", "rotating", "mechanical"]
    assert all(a.quality.accepted and a.estimator_succeeded for a in nominal.attempts)


def test_recorded_configuration_matches_actual_provider_seed_and_bus(nominal):
    for stage, seed in (("standstill", 1901), ("rotating", 1902), ("mechanical", 1903)):
        config = getattr(nominal.config, stage)
        assert config.seed == seed and config.dc_bus_voltage_v == nominal.config.dc_bus_voltage_v
        first = next(r for r in nominal.measurement_records if r.stage.value == stage)
        assert first.config == config


def test_all_six_estimates_propagate_without_truth_fallback(nominal):
    full = nominal.commissioning
    expected = full.retuned_controller_parameters(nominal.config.prior_assumptions.parameters())
    assert asdict(nominal.controller_parameters) == asdict(expected)
    for key in ("Rs", "Ld", "Lq", "psi_f", "J", "B"):
        assert getattr(nominal.controller_parameters, key) != getattr(nominal.simulation_evaluation.truth, key)
    assert nominal.controller_parameters.pole_pairs == nominal.config.prior_assumptions.pole_pairs


def test_controller_constants_are_from_original_constructors(nominal):
    parameters = nominal.controller_parameters.parameters()
    current = CurrentFOCController(parameters, dc_bus_voltage=nominal.config.dc_bus_voltage_v)
    speed = SpeedController(parameters, iq_limit=nominal.config.current_limit_a)
    c, s = nominal.controller_constants.current, nominal.controller_constants.speed
    assert (c.kp_d, c.ki_d, c.kp_q, c.ki_q, c.anti_windup_gain) == (
        current.pi_d.kp, current.pi_d.ki, current.pi_q.kp, current.pi_q.ki, current.anti_windup_gain)
    assert (s.kp, s.ki, s.torque_constant_nm_per_a, s.iq_limit_a) == (speed.kp, speed.ki, speed.kt, nominal.config.current_limit_a)


def test_steady_result_equals_direct_M14(nominal):
    cfg = nominal.config
    direct = assess_operating_point(nominal.commissioning, OperatingPointRequest(
        cfg.speed_target_rpm, cfg.load_torque_nm, cfg.dc_bus_voltage_v, cfg.current_limit_a))
    assert nominal.steady_feasibility == direct


def test_dynamic_result_equals_direct_M16(nominal):
    cfg = nominal.config
    direct = assess_dynamic_operating_point(nominal.commissioning, DynamicOperatingRequest(0,
        cfg.speed_target_rpm, cfg.load_torque_nm, cfg.dc_bus_voltage_v, cfg.current_limit_a,
        cfg.deadline_s, hold_time_s=cfg.hold_time_s), DynamicAnalysisConfig(simulation_dt_s=cfg.simulation_dt_s))
    assert nominal.dynamic_feasibility == direct
    assert "physical_deadline_not_ruled_out" not in vars(direct.quasi_steady)


def test_control_trace_is_direct_simulation_with_accepted_parameters(nominal):
    cfg = nominal.config
    direct = run_speed_foc_simulation(plant_params=cfg.simulation_truth.parameters(),
        controller_params=nominal.controller_parameters.parameters(), dt=cfg.simulation_dt_s,
        simulation_time=cfg.simulation_duration_s, speed_ref_rpm=cfg.speed_target_rpm,
        load_step_time=cfg.load_step_time_s, load_step_torque=cfg.load_torque_nm,
        dc_bus_voltage=cfg.dc_bus_voltage_v, current_limit_a=cfg.current_limit_a,
        nonidealities=nominal.nonidealities)
    for key in ("rpm", "iq", "voltage_magnitude", "voltage_saturated"):
        np.testing.assert_array_equal(nominal.control.trace[key], direct[key])
        assert not nominal.control.trace[key].flags.writeable
    assert "plant_params" not in nominal.control.trace


def test_rejected_result_preserves_prior_and_blocks_downstream(rejected, tmp_path):
    assert rejected.status == "REJECTED"
    assert "standstill.excessive_residual" in rejected.quality.rejection_reasons
    assert any(a.estimate is not None for a in rejected.attempts)
    assert rejected.controller_parameters == rejected.config.prior_assumptions
    assert rejected.steady_feasibility is rejected.dynamic_feasibility is rejected.control is rejected.firmware_config is None
    with pytest.raises(CommissioningRejectedError): export_firmware_configuration(rejected, tmp_path/"invalid.h")
    assert not (tmp_path/"invalid.h").exists()


def test_header_matches_M18_exporter(nominal, tmp_path):
    actual = export_firmware_configuration(nominal, tmp_path/"actual.h")
    cfg = build_firmware_config(nominal.commissioning, dc_bus_voltage_v=nominal.config.dc_bus_voltage_v,
                                iq_limit_a=nominal.config.current_limit_a)
    expected = export_c_header(cfg, tmp_path/"expected.h", provenance=f"SIMULATED accepted full commissioning; project {__version__}; seed 1901; scenario ideal.")
    assert actual.read_bytes() == expected.read_bytes()
    assert nominal.firmware_config == cfg


def test_export_configuration_failure_is_distinct_from_gate_rejection(nominal, tmp_path):
    unavailable = replace(nominal, firmware_config=None)
    with pytest.raises(ValueError, match="firmware_configuration_unavailable"):
        export_firmware_configuration(unavailable, tmp_path/"missing.h")
    assert unavailable.quality.accepted


def test_accepted_but_unavailable_validation_plot_does_not_claim_rejection(nominal):
    from src.engineering_reporting import control_figure
    unavailable = replace(nominal, control=None, warnings=("workflow.control_unavailable: numerical failure",))
    figure = control_figure(unavailable)
    text = " ".join(t.get_text() for ax in figure.axes for t in ax.texts)
    assert "FULL ACCEPTED" in text and "accepted controller update retained" in text
    assert "workflow.control_unavailable" in text
    assert "Prior controller retained" not in text
    assert unavailable.firmware_available
    figure.clear()


def test_deterministic_seed_reproduces_measurements_estimates_and_trace(nominal):
    repeated = run_engineering_workflow(nominal.config)
    assert nominal.controller_parameters == repeated.controller_parameters
    assert nominal.quality == repeated.quality
    assert nominal.control.metrics == repeated.control.metrics
    for a, b in zip(nominal.measurement_records, repeated.measurement_records):
        np.testing.assert_array_equal(a.measurements.current_q_a, b.measurements.current_q_a)
    np.testing.assert_array_equal(nominal.control.trace["rpm"], repeated.control.trace["rpm"])


def test_adaptive_retains_actual_retry_history():
    base = EngineeringWorkflowConfig(mode="adaptive")
    config = replace(base, standstill=replace(base.standstill, d_voltage_v=.096, q_voltage_v=.112))
    result = run_engineering_workflow(config)
    assert result.quality.accepted
    assert result.supervisor.accepted
    first, second = result.attempts[:2]
    assert not first.quality.accepted and second.quality.accepted
    assert first.retry_action == "increase_standstill_voltage"
    assert first.next_config == second.config
    assert result.attempts == result.supervisor.attempts
    assert len(result.measurement_records) == len(result.attempts)


def test_adaptive_rejection_is_retained_and_does_not_export():
    result = run_engineering_workflow(EngineeringWorkflowConfig(mode="adaptive", scenario="timing_one_sample"))
    assert not result.quality.accepted and not result.firmware_available
    assert result.supervisor.terminal_reason == "standstill.model_residual_terminal"
    assert result.attempts[0].retry_decision == "terminal"


def test_nonideality_uses_exact_M17_chain_and_truth_stays_separate():
    from experiments.nonideality_robustness import scenarios
    result = run_engineering_workflow(EngineeringWorkflowConfig(scenario="current_strong"))
    assert result.nonidealities == next(s.errors for s in scenarios() if s.name == "current_strong")
    assert result.quality.accepted  # preserve the M17 silent-bias failure mode
    assert not np.array_equal(result.control.trace["measured_iq"], result.control.trace["iq"])
    assert max(result.simulation_evaluation.parameter_absolute_error_percent.values()) > 10
    assert any("does not prove" in w for w in result.warnings)
    for record in result.measurement_records:
        assert "plant" not in vars(record.measurements) and "true_torque" not in vars(record.measurements)
    assert "simulation_truth" not in vars(result.controller_constants)


def test_provider_failure_keeps_electrical_estimates_and_does_not_retune():
    base = EngineeringWorkflowConfig()
    result = run_engineering_workflow(replace(base, mechanical=replace(base.mechanical, current_reference_limit_a=.1)))
    assert not result.quality.accepted
    assert result.commissioning.electrical.quality.accepted
    assert result.attempts[-1].quality.estimator_failure
    assert result.measurement_records[-1].measurement_failure
    assert result.controller_parameters == base.prior_assumptions


def test_accepted_quality_does_not_hide_operating_infeasibility():
    result = run_engineering_workflow(EngineeringWorkflowConfig(speed_target_rpm=2000))
    assert result.quality.accepted
    assert result.steady_feasibility.classification == "voltage_limited"
    assert not result.dynamic_feasibility.controller.predicted_closed_loop_success
    assert not result.control.metrics["control_success"]
    assert result.control.metrics["command_saturation_fraction"] > 0
    assert result.firmware_available  # exporter verifies quality, not hardware operation


def test_operation_only_bus_sag_does_not_change_commissioning(nominal):
    result = run_engineering_workflow(EngineeringWorkflowConfig(scenario="bus_sag_strong", exposure="operation_only"))
    assert result.controller_parameters == nominal.controller_parameters
    assert result.control.trace["actual_dc_bus_voltage"] == pytest.approx(21.6)
    assert result.control.trace["dc_bus_voltage"] == 24


@pytest.mark.parametrize("setting", [dict(seed=-1), dict(mode="fake"), dict(scenario="fake"),
    dict(dc_bus_voltage_v=0), dict(speed_target_rpm=0), dict(load_step_time_s=.6), dict(current_limit_a=0)])
def test_invalid_application_inputs_are_explicit(setting):
    with pytest.raises(ValueError): EngineeringWorkflowConfig(**setting)
