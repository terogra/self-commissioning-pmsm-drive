from dataclasses import asdict, replace
from math import pi, sqrt
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.operating_feasibility import (
    commission_plant, compare_case, confusion, dynamic_metrics, oracle_prediction,
    reanalyze_pr8, validation_requests,
)
from src.commissioning_quality import CommissioningQuality
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point, operating_envelope
from src.speed_foc_simulation import run_speed_foc_simulation


@pytest.fixture(scope="module")
def motor():
    plant = PMSMParameters(Rs=.56, Ld=.0014, Lq=.0008, psi_f=.015, J=.0005, B=.0003)
    return plant, commission_plant(plant)


@pytest.mark.parametrize("speed,load,bus,limit,classification", [
    (250, .02, 24, 3, "feasible"), (2000, .05, 12, 5, "voltage_limited"),
    (250, .5, 48, 1, "current_limited"), (2500, .5, 12, 1, "both_limited"),
    (0, .02, 24, 3, "feasible"), (1000, 0, 24, 5, "feasible"),
    (0, 0, 24, 5, "feasible"),
])
def test_operating_categories_and_physical_equations(motor, speed, load, bus, limit, classification):
    _, full = motor
    r = assess_operating_point(full, OperatingPointRequest(speed, load, bus, limit))
    assert r.classification == classification
    e, f, m = full.electrical.electrical, full.electrical.flux, full.mechanical.estimate
    p = full.electrical.pole_pairs
    omega = speed*2*pi/60
    assert r.required_torque_nm == pytest.approx(load + m.B*omega)
    assert 1.5*p*f.psi_f*r.required_iq_a == pytest.approx(r.required_torque_nm)
    assert r.required_vd_v == pytest.approx(-p*omega*e.Lq*r.required_iq_a)
    assert r.required_vq_v == pytest.approx(e.Rs*r.required_iq_a+p*omega*f.psi_f)
    assert r.voltage_limit_v == pytest.approx(bus/sqrt(3))
    assert r.voltage_margin_v == pytest.approx(r.voltage_limit_v-r.required_voltage_magnitude_v)
    assert r.current_margin_a == pytest.approx(limit-r.required_current_magnitude_a)
    assert r.voltage_utilization == pytest.approx(r.required_voltage_magnitude_v/r.voltage_limit_v)
    assert r.current_utilization == pytest.approx(r.required_current_magnitude_a/limit)
    assert r.feasible == (r.current_feasible and r.voltage_feasible)
    for key, value in asdict(r).items():
        if isinstance(value, (int, float)):
            assert np.isfinite(value), key


@pytest.mark.parametrize("field,value", [
    ("speed_rpm", -1), ("load_torque_nm", -1), ("dc_bus_voltage_v", -1), ("current_limit_a", -1),
    ("speed_rpm", float("nan")), ("load_torque_nm", float("nan")),
    ("dc_bus_voltage_v", float("nan")), ("current_limit_a", float("nan")),
    ("speed_rpm", float("inf")), ("dc_bus_voltage_v", 0), ("current_limit_a", 0),
])
def test_invalid_requests_are_explicit(field, value):
    with pytest.raises(ValueError, match="operating.invalid_request"):
        OperatingPointRequest(**{**dict(speed_rpm=1000, load_torque_nm=.05, dc_bus_voltage_v=24, current_limit_a=5), field: value})


def test_no_J_Ld_or_hidden_plant_access_and_quality_not_changed(motor):
    plant, full = motor
    request = OperatingPointRequest(1000, .05, 12, 5)
    original = full.quality
    prediction = assess_operating_point(full, request)
    modified = replace(full, mechanical=replace(full.mechanical, estimate=replace(full.mechanical.estimate, J=1234.0)))
    assert assess_operating_point(modified, request) == prediction
    # This object has no plant, J, Ld, prior assumptions, or post-hoc outcome.
    # It carries only the accepted-result shape and identified steady-state inputs.
    only_estimates = SimpleNamespace(quality=full.quality,
        electrical=SimpleNamespace(electrical=SimpleNamespace(Rs=full.electrical.electrical.Rs, Lq=full.electrical.electrical.Lq),
                                   flux=SimpleNamespace(psi_f=full.electrical.flux.psi_f), pole_pairs=4),
        mechanical=SimpleNamespace(estimate=SimpleNamespace(B=full.mechanical.estimate.B)))
    assert assess_operating_point(only_estimates, request) == prediction
    # Mutating the independent hidden plant cannot change the stored estimate result.
    unrelated = replace(plant, Rs=20, Lq=.2, psi_f=.2, J=10, B=10)
    assert unrelated != plant
    assert assess_operating_point(full, request) == prediction
    assert full.quality == original
    assert full.electrical.quality.accepted and full.mechanical.quality.accepted


def test_rejected_commissioning_is_unavailable_not_operating_infeasible(motor):
    _, full = motor
    rejected = replace(full, mechanical=replace(full.mechanical,
                       quality=CommissioningQuality(False, ("mechanical.relative_uncertainty",))))
    with pytest.raises(ValueError, match="operating.commissioning_not_accepted"):
        assess_operating_point(rejected, OperatingPointRequest(100, 0, 48, 5))
    assert rejected.mechanical.quality.rejection_reasons == ("mechanical.relative_uncertainty",)


def test_limits_are_monotonic_and_equality_is_included(motor):
    _, full = motor
    request = OperatingPointRequest(1000, .05, 12, .5)
    before = assess_operating_point(full, request)
    larger_bus = assess_operating_point(full, replace(request, dc_bus_voltage_v=48))
    larger_current = assess_operating_point(full, replace(request, current_limit_a=5))
    assert larger_bus.voltage_margin_v > before.voltage_margin_v
    assert larger_bus.voltage_feasible >= before.voltage_feasible
    assert larger_current.current_feasible >= before.current_feasible
    assert larger_current.current_margin_a > before.current_margin_a
    assert larger_current.required_voltage_magnitude_v == before.required_voltage_magnitude_v
    boundary = assess_operating_point(full, replace(request, current_limit_a=before.required_current_magnitude_a))
    assert boundary.current_feasible and boundary.current_margin_a == 0
    inside = assess_operating_point(full, replace(request, dc_bus_voltage_v=before.required_voltage_magnitude_v*sqrt(3)*(1+1e-10)))
    outside = assess_operating_point(full, replace(request, dc_bus_voltage_v=before.required_voltage_magnitude_v*sqrt(3)*(1-1e-10)))
    assert inside.voltage_feasible and not outside.voltage_feasible


def test_oracle_agreement_and_deterministic_envelope(motor):
    plant, full = motor
    speeds, loads = [0, 250, 1000, 2500], [0, .05, .5]
    first = operating_envelope(full, speeds, loads, 12, 1)
    assert first == operating_envelope(full, speeds, loads, 12, 1)
    assert len(first) == len(speeds)*len(loads)
    for result in first:
        oracle = oracle_prediction(plant, OperatingPointRequest(result.requested_speed_rpm, result.requested_load_torque_nm, 12, 1))
        assert result.classification == oracle.classification
        assert result.required_voltage_magnitude_v == pytest.approx(oracle.required_voltage_magnitude_v, rel=.01)


def test_configurable_reference_limit_preserves_default_and_is_used():
    kwargs = dict(simulation_time=.02, load_step_time=.01)
    baseline = run_speed_foc_simulation(**kwargs)
    explicit = run_speed_foc_simulation(**kwargs, current_limit_a=5)
    limited = run_speed_foc_simulation(**kwargs, current_limit_a=.3)
    np.testing.assert_array_equal(baseline["rpm"], explicit["rpm"])
    assert np.max(np.abs(limited["iq_ref"])) <= .3
    for limit in (0, -1, float("nan")):
        with pytest.raises(ValueError, match="current_limit_a"):
            run_speed_foc_simulation(**kwargs, current_limit_a=limit)


def test_dynamic_failure_is_distinct_from_feasible_steady_state(motor):
    plant, full = motor
    request = validation_requests(full)["acceleration_limited"]
    row, sim = compare_case(plant, full, request)
    assert row["steady_state_feasible"]
    assert not row["closed_loop_dynamic_success"]
    assert row["extended_run_success"] is True
    assert full.quality.accepted
    assert dynamic_metrics(sim)["closed_loop_dynamic_success"] is False
    assert confusion([row])["false_feasible"] == 1


def test_pr8_accepted_failures_replayed_and_detected():
    rows = reanalyze_pr8()
    assert len(rows) == 13
    evaluated = [r for r in rows if r["status"] == "evaluated"]
    assert len(evaluated) == 5
    assert [r["case_id"] for r in evaluated if not r["steady_state_feasible"]] == [0, 1, 5, 7]
    assert sum(r["steady_state_feasible"] for r in evaluated) == 1
    assert all(r["commissioning_accepted"] for r in evaluated)
    assert all(r["steady_state_feasible"] == r["oracle_steady_state_feasible"] == r["closed_loop_dynamic_success"] for r in evaluated)
