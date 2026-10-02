"""Dynamic predictions consume estimates, independently of truth and quality policy."""

from dataclasses import replace
import inspect
from math import pi, sqrt
from types import SimpleNamespace as NS

import numpy as np
import pytest

import src.dynamic_feasibility as dynamic
from src.dynamic_feasibility import (
    DynamicAnalysisConfig, DynamicOperatingRequest, assess_dynamic_operating_point,
    assess_physical_capability, evaluate_controller_trace,
)
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.speed_foc_simulation import run_speed_foc_simulation


@pytest.fixture
def estimates():
    # Deliberately contains neither a plant object nor accuracy/outcome labels.
    return NS(quality=NS(accepted=True), electrical=NS(
        electrical=NS(Rs=.56, Ld=.0014, Lq=.0008), flux=NS(psi_f=.015), pole_pairs=4),
        mechanical=NS(estimate=NS(J=.0005, B=.0003)))


def request(**kwargs):
    return DynamicOperatingRequest(**{**dict(initial_speed_rpm=0, target_speed_rpm=1000,
        load_torque_nm=.005, dc_bus_voltage_v=48, current_limit_a=.4446658, deadline_s=.6), **kwargs})


@pytest.mark.parametrize("field,value", [
    ("initial_speed_rpm", -1), ("target_speed_rpm", 0), ("load_torque_nm", -1),
    ("dc_bus_voltage_v", 0), ("current_limit_a", 0), ("deadline_s", 0),
    ("hold_time_s", 0), ("minimum_speed_tolerance_rpm", 0),
    ("speed_tolerance_fraction", 1), ("speed_tolerance_fraction", -1),
    ("initial_speed_rpm", 1000), ("target_speed_rpm", float("inf")),
    ("deadline_s", float("nan")), ("current_limit_a", True), ("deadline_s", "1"),
])
def test_invalid_forward_requests(field, value):
    with pytest.raises(ValueError, match="dynamic."):
        request(**{field: value})


def test_missing_or_rejected_estimates_are_explicit(estimates):
    estimates.quality.accepted = False
    with pytest.raises(ValueError, match="commissioning_not_accepted"):
        assess_dynamic_operating_point(estimates, request())
    estimates.quality.accepted = True
    estimates.mechanical.estimate = None
    with pytest.raises(ValueError, match="missing_full_estimates"):
        assess_dynamic_operating_point(estimates, request())


def test_physics_monotonicity_and_analytic_integral(estimates):
    r = request()
    baseline = assess_physical_capability(estimates, r)
    assert baseline.integration_converged
    estimates.mechanical.estimate.J *= 2
    assert assess_physical_capability(estimates, r).optimistic_min_transition_time_s == pytest.approx(
        2*baseline.optimistic_min_transition_time_s)
    estimates.mechanical.estimate.J /= 2
    for changed in (replace(r, current_limit_a=1), replace(r, dc_bus_voltage_v=96)):
        assert assess_physical_capability(estimates, changed).optimistic_min_transition_time_s <= baseline.optimistic_min_transition_time_s
    estimates.mechanical.estimate.B = 0
    p = assess_physical_capability(estimates, r)
    expected = r.lower_band_rpm*2*pi/60*estimates.mechanical.estimate.J / (
        1.5*4*.015*r.current_limit_a-r.load_torque_nm)
    assert p.optimistic_min_transition_time_s == pytest.approx(expected, rel=1e-12)
    assert p.optimistic_min_completion_time_s == pytest.approx(expected+r.hold_time_s)


def test_voltage_root_domain_limits_and_coincidence(estimates):
    model = dynamic._commissioned_model(estimates)
    r = request(target_speed_rpm=1500, current_limit_a=5, dc_bus_voltage_v=12)
    p = assess_physical_capability(estimates, r)
    assert p.current_limited_on_path and p.voltage_limited_on_path
    assert not p.tolerance_band_reachable and p.limiting_speed_rpm < r.lower_band_rpm
    assert "dynamic.nonpositive_acceleration" in p.reasons
    for point in p.trajectory:
        omega_e = 4*point.speed_rpm*2*pi/60
        if point.nonnegative_voltage_domain:
            voltage = np.hypot(-omega_e*.0008*point.available_iq_a,
                               .56*point.available_iq_a+omega_e*.015)
            assert voltage <= 12/sqrt(3)*(1+1e-12)
        assert 0 <= point.available_iq_a <= 5
    zero = dynamic._capability_point(model, r, 0)
    assert zero.voltage_limited_iq_a == pytest.approx(12/sqrt(3)/.56)
    coincident = dynamic._capability_point(model, replace(r, current_limit_a=zero.voltage_limited_iq_a), 0)
    assert coincident.limiting_factor == "coincident"
    emf_boundary = 12/sqrt(3)/(.015*4)*60/(2*pi)
    outside = dynamic._capability_point(model, r, emf_boundary*(1+1e-8))
    assert not outside.nonnegative_voltage_domain and outside.available_iq_a == 0


def test_steady_feasible_deadline_failure_and_recovery(estimates):
    before = vars(estimates.mechanical.estimate).copy()
    short = assess_dynamic_operating_point(estimates, request())
    long = assess_dynamic_operating_point(estimates, request(deadline_s=4))
    longer = assess_dynamic_operating_point(estimates, request(deadline_s=4.1))
    assert short.exact_target_steady_state.feasible
    assert not short.physical.physical_deadline_not_ruled_out
    assert not short.controller.predicted_closed_loop_success
    assert long.controller.predicted_closed_loop_success and longer.controller.predicted_closed_loop_success
    assert long.controller.hold_completion_time_s <= 4
    assert long.controller.qualified_band_entry_time_s == longer.controller.qualified_band_entry_time_s
    assert vars(estimates.mechanical.estimate) == before and estimates.quality.accepted


def test_exact_target_and_band_are_distinct(estimates):
    steady = assess_operating_point(estimates, OperatingPointRequest(1000, .05, 48, 5))
    r = request(load_torque_nm=.05, current_limit_a=5,
                dc_bus_voltage_v=steady.required_voltage_magnitude_v*sqrt(3)*.995)
    result = assess_dynamic_operating_point(estimates, r)
    assert not result.exact_target_steady_state.feasible
    assert result.tolerance_band_steady_state.feasible
    assert result.physical.tolerance_band_reachable
    assert "dynamic.exact_target_steady_infeasible" in result.reasons


def test_no_truth_or_retry_access_identified_model_only(estimates, monkeypatch):
    calls = []
    original = dynamic.run_speed_foc_simulation
    def spy(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(dynamic, "run_speed_foc_simulation", spy)
    assess_dynamic_operating_point(estimates, request(deadline_s=.01))
    assert list(inspect.signature(assess_dynamic_operating_point).parameters) == ["commissioning", "request", "config"]
    model = calls[0]["plant_params"]
    assert model is calls[0]["controller_params"]
    assert vars(model) == dict(Rs=.56, Ld=.0014, Lq=.0008, psi_f=.015, J=.0005, B=.0003, pole_pairs=4)
    assert calls[0]["load_step_time"] == 0 and calls[0]["load_step_torque"] == .005
    # No supervisor provider, attempt state, gate, or post-hoc truth enters this layer.
    source = inspect.getsource(dynamic)
    assert "adaptive_commissioning" not in source and "electromagnetic_torque(" not in source


def test_brief_crossing_is_not_a_hold_and_hold_must_fit_deadline():
    r = request(target_speed_rpm=100, deadline_s=.3)
    dt = .01
    speed = np.r_[np.zeros(9), [100, 100], np.zeros(19)]
    sim = dict(time=np.arange(30)*dt, rpm=speed, id=np.zeros(30), iq=np.zeros(30),
        iq_ref=np.zeros(30), voltage_d=np.zeros(30), voltage_q=np.zeros(30),
        voltage_magnitude=np.zeros(30), voltage_saturated=np.zeros(30, dtype=bool), voltage_limit=10)
    p = evaluate_controller_trace(sim, r, dt)
    assert p.first_band_entry_time_s == pytest.approx(.1)
    assert not p.predicted_closed_loop_success and p.hold_completion_time_s is None
    sim["rpm"][:] = 100
    assert evaluate_controller_trace(sim, r, dt).predicted_closed_loop_success
    assert not evaluate_controller_trace(sim, replace(r, deadline_s=.05), dt).predicted_closed_loop_success
    sim["iq_ref"][5] = 100
    assert not evaluate_controller_trace(sim, r, dt).predicted_closed_loop_success
    sim["iq_ref"][:] = 0
    sim["iq"][5] = float("nan")
    assert not evaluate_controller_trace(sim, r, dt).finite_signals


def test_initial_speed_extension_preserves_historical_default():
    sim = run_speed_foc_simulation(simulation_time=.02, load_step_time=.01)
    explicit = run_speed_foc_simulation(simulation_time=.02, load_step_time=.01, initial_speed_rpm=0)
    # Recorded from unmodified main 363b70d before the extension.
    expected = [0.013571705286833402, 124.49828706299103, 338.6224806234978, 670.324880555551]
    np.testing.assert_allclose(sim["rpm"][[0, 199, 499, 999]], expected, rtol=1e-12, atol=1e-10)
    for key in ("rpm", "id", "iq", "iq_ref", "voltage_magnitude", "voltage_saturated"):
        np.testing.assert_array_equal(sim[key], explicit[key])
    moving = run_speed_foc_simulation(simulation_time=.002, load_step_time=0, initial_speed_rpm=500)
    assert moving["rpm"][0] > 499 and moving["initial_speed_rpm"] == 500


def test_resolution_warning_and_already_in_band(estimates):
    coarse = DynamicAnalysisConfig(initial_path_points=3, maximum_path_points=3)
    result = assess_physical_capability(estimates, request(), coarse)
    assert result.physical_deadline_not_ruled_out is None
    assert "dynamic.integration_resolution" in result.reasons
    band = assess_physical_capability(estimates, request(initial_speed_rpm=995, deadline_s=.2))
    assert band.optimistic_min_transition_time_s == 0
    assert band.physical_deadline_not_ruled_out


def test_voltage_limit_actively_improves_bound_and_numeric_refinement(estimates):
    low = request(current_limit_a=5, dc_bus_voltage_v=12)
    before = assess_physical_capability(estimates, low)
    after = assess_physical_capability(estimates, replace(low, dc_bus_voltage_v=24))
    fine = assess_physical_capability(estimates, low, DynamicAnalysisConfig(relative_time_tolerance=1e-5))
    assert before.voltage_limited_on_path and before.tolerance_band_reachable
    assert after.optimistic_min_transition_time_s < before.optimistic_min_transition_time_s
    assert fine.integration_converged
    assert before.optimistic_min_transition_time_s == pytest.approx(fine.optimistic_min_transition_time_s, rel=.001)


@pytest.mark.parametrize("kwargs", [dict(simulation_dt_s=float("nan")), dict(simulation_dt_s="a"),
    dict(initial_path_points=2), dict(maximum_path_points=3), dict(trace_interval_s=0)])
def test_invalid_analysis_configs(kwargs):
    with pytest.raises(ValueError, match="invalid_analysis_config"):
        DynamicAnalysisConfig(**kwargs)


def test_population_design_and_scoring_are_deterministic(estimates):
    from experiments.dynamic_operating_feasibility import requests, summary
    a = requests(estimates, np.random.default_rng(45))
    assert a == requests(estimates, np.random.default_rng(45))
    assert a != requests(estimates, np.random.default_rng(46))
    assert a["deadline_limited"].current_limit_a == a["longer_deadline"].current_limit_a
    s = summary([dict(status="commissioning_unavailable")])
    assert s["total_cases"] == s["unavailable_or_error_cases"] == 1


def test_adaptive_history_and_quality_unchanged_by_dynamic_failure():
    from tests.test_adaptive_commissioning import run
    # The supervisor and its providers finish before the separate dynamic call.
    supervised = run()
    attempts = supervised.attempts
    counts = supervised.attempt_counts.copy()
    quality = supervised.full_commissioning.quality
    state = supervised.state
    result = assess_dynamic_operating_point(supervised.full_commissioning, request(deadline_s=.001))
    assert not result.controller.predicted_closed_loop_success
    assert supervised.attempts == attempts and supervised.attempt_counts == counts
    assert supervised.state == state and supervised.full_commissioning.quality == quality
