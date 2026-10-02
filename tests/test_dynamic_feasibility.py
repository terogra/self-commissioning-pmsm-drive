"""Dynamic predictions consume estimates, independently of truth and quality policy."""

from dataclasses import fields, replace
import csv
import inspect
import json
from math import pi, sqrt
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

import src.dynamic_feasibility as dynamic
from src.dynamic_feasibility import (
    DynamicAnalysisConfig, DynamicOperatingRequest, assess_dynamic_operating_point,
    assess_quasi_steady_capability, evaluate_controller_trace,
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


def test_quasi_steady_monotonicity_and_analytic_integral(estimates):
    r = request()
    baseline = assess_quasi_steady_capability(estimates, r)
    assert baseline.integration_converged
    estimates.mechanical.estimate.J *= 2
    assert assess_quasi_steady_capability(estimates, r).quasi_steady_transition_time_estimate_s == pytest.approx(
        2*baseline.quasi_steady_transition_time_estimate_s)
    estimates.mechanical.estimate.J /= 2
    for changed in (replace(r, current_limit_a=1), replace(r, dc_bus_voltage_v=96)):
        assert assess_quasi_steady_capability(estimates, changed).quasi_steady_transition_time_estimate_s <= baseline.quasi_steady_transition_time_estimate_s
    estimates.mechanical.estimate.B = 0
    p = assess_quasi_steady_capability(estimates, r)
    expected = r.lower_band_rpm*2*pi/60*estimates.mechanical.estimate.J / (
        1.5*4*.015*r.current_limit_a-r.load_torque_nm)
    assert p.quasi_steady_transition_time_estimate_s == pytest.approx(expected, rel=1e-12)
    assert p.quasi_steady_completion_time_estimate_s == pytest.approx(expected+r.hold_time_s)


def test_voltage_root_domain_limits_and_coincidence(estimates):
    model = dynamic._commissioned_model(estimates)
    r = request(target_speed_rpm=1500, current_limit_a=5, dc_bus_voltage_v=12)
    p = assess_quasi_steady_capability(estimates, r)
    assert p.current_limited_on_path and p.voltage_limited_on_path
    assert not p.quasi_steady_band_reachable and p.limiting_speed_rpm < r.lower_band_rpm
    assert "dynamic.quasi_steady_nonpositive_acceleration" in p.reasons
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
    assert not short.quasi_steady.quasi_steady_deadline_met
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
    assert result.quasi_steady.quasi_steady_band_reachable
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
    result = assess_quasi_steady_capability(estimates, request(), coarse)
    assert result.quasi_steady_deadline_met is None
    assert "dynamic.quasi_steady_integration_resolution" in result.reasons
    band = assess_quasi_steady_capability(estimates, request(initial_speed_rpm=995, deadline_s=.2))
    assert band.quasi_steady_transition_time_estimate_s == 0
    assert band.quasi_steady_deadline_met


def test_voltage_limit_actively_reduces_estimate_and_numeric_refinement(estimates):
    low = request(current_limit_a=5, dc_bus_voltage_v=12)
    before = assess_quasi_steady_capability(estimates, low)
    after = assess_quasi_steady_capability(estimates, replace(low, dc_bus_voltage_v=24))
    fine = assess_quasi_steady_capability(estimates, low, DynamicAnalysisConfig(relative_time_tolerance=1e-5))
    assert before.voltage_limited_on_path and before.quasi_steady_band_reachable
    assert after.quasi_steady_transition_time_estimate_s < before.quasi_steady_transition_time_estimate_s
    assert fine.integration_converged
    assert before.quasi_steady_transition_time_estimate_s == pytest.approx(fine.quasi_steady_transition_time_estimate_s, rel=.001)


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


RESULTS = Path(__file__).resolve().parents[1]/"results/dynamic_operating_feasibility"


def saved_held_out_rows():
    with (RESULTS/"held_out.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_original_evidence_disproves_a_universal_lower_bound():
    # Read original records, not a newly drawn/replacement evaluation population.
    rows = saved_held_out_rows()
    actual_early, same_model_early = [], []
    for row in rows:
        estimate = row["quasi_steady_transition_time_estimate_s"]
        if not estimate:
            continue
        for key, cases in (("actual_first_entry_s", actual_early),
                           ("prediction_first_entry_s", same_model_early)):
            if row[key] and float(row[key]) < float(estimate):
                cases.append((row["motor_id"], row["scenario"]))
    assert len(rows) == 40
    assert actual_early == [("3", "longer_deadline"), ("4", "voltage_high_speed"), ("4", "tolerance_boundary")]
    assert same_model_early == [("3", "voltage_high_speed"), ("4", "voltage_high_speed"), ("4", "tolerance_boundary")]
    # Two of the three hidden-plant counterexamples are also same-model ones.
    assert set(actual_early) & set(same_model_early) == {("4", "voltage_high_speed"), ("4", "tolerance_boundary")}
    summary = json.loads((RESULTS/"summary.json").read_text(encoding="utf-8"))
    assert summary["held_out"]["actual_entry_before_quasi_steady_estimate"] == 3
    assert "Naming corrected after the original held-out finding" in summary["semantics_correction"]


@pytest.mark.parametrize("scenario", ["voltage_high_speed", "tolerance_boundary"])
def test_same_model_can_beat_estimate_and_meet_a_model_missed_deadline(scenario):
    row = next(r for r in saved_held_out_rows() if r["motor_id"] == "4" and r["scenario"] == scenario)
    audit = json.loads((RESULTS/"held_out_plants.json").read_text(encoding="utf-8"))[4]
    # Only the saved identified model is used; hidden plant truth is unnecessary.
    model = audit["identified"]
    accepted = NS(quality=NS(accepted=True), electrical=NS(
        electrical=NS(**{k: model[k] for k in ("Rs", "Ld", "Lq")}),
        flux=NS(psi_f=model["psi_f"]), pole_pairs=model["pole_pairs"]),
        mechanical=NS(estimate=NS(J=model["J"], B=model["B"])))
    req = DynamicOperatingRequest(**{k: float(row[k]) for k in DynamicOperatingRequest.__dataclass_fields__})
    result = assess_dynamic_operating_point(accepted, req)
    qs = result.quasi_steady
    assert qs.quasi_steady_transition_time_estimate_s == pytest.approx(float(row["quasi_steady_transition_time_estimate_s"]), abs=1e-12)
    assert result.controller.first_band_entry_time_s == pytest.approx(float(row["prediction_first_entry_s"]), abs=1e-12)
    assert result.controller.first_band_entry_time_s < qs.quasi_steady_transition_time_estimate_s
    # A unit-test counterexample using the SAME original model/request, only a
    # deadline between its two completion times. This is not a new population.
    deadline = .5*(qs.quasi_steady_completion_time_estimate_s+result.controller.hold_completion_time_s)
    counterexample = assess_dynamic_operating_point(accepted, replace(req, deadline_s=deadline))
    assert counterexample.quasi_steady.quasi_steady_deadline_met is False
    assert "dynamic.quasi_steady_deadline_exceeded" in counterexample.quasi_steady.reasons
    assert counterexample.controller.predicted_closed_loop_success


def test_api_and_documentation_scope_estimates_to_quasi_steady_model():
    names = {f.name for f in fields(dynamic.QuasiSteadyCapability)}
    assert {"quasi_steady_transition_time_estimate_s", "quasi_steady_completion_time_estimate_s",
            "quasi_steady_deadline_met", "quasi_steady_band_reachable"} <= names
    assert not any("physical" in n or "optimistic_min" in n for n in names)
    assert not hasattr(dynamic, "PhysicalCapability") and not hasattr(dynamic, "assess_physical_capability")
    assert "physical" not in {f.name for f in fields(dynamic.DynamicFeasibilityResult)}
    root = RESULTS.parents[1]
    for name in ("README.md", "docs/engineering_log.md", "docs/dynamic_feasibility_protocol.md"):
        text = (root/name).read_text(encoding="utf-8")
        # These required cautions must survive documentation changes.
        assert "full dq transient simulation" in text
        assert "not a physical minimum or universal lower bound" in text.replace("\n", " ")
        assert "optimistic lower-bound interpretation" not in text
