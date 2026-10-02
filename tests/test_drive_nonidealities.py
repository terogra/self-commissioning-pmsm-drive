"""Signal-chain tests: no changes to estimators, gates, or controller design."""

from dataclasses import FrozenInstanceError, fields, replace
import ast
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from src.drive_nonidealities import (
    ActuationErrors, CurrentMeasurementErrors, DriveNonidealities, FeedbackDelay,
    FrameErrors, OperatingDrift, TimingErrors, VoltageMeasurementErrors,
    apply_voltage, delayed_samples, estimator_voltage, measure_current, quantize,
)
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.motor import PMSMParameters
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation
from src.transforms import inverse_park_transform, inverse_clarke_transform, clarke_transform, park_transform


IDEAL = DriveNonidealities()


@pytest.mark.parametrize("factory", [
    lambda: CurrentMeasurementErrors(phase_gains=(1, 0, 1)),
    lambda: CurrentMeasurementErrors(phase_offsets_a=(0, np.nan, 0)),
    lambda: CurrentMeasurementErrors(quantum_a=-1),
    lambda: VoltageMeasurementErrors(dq_gains=[1, 1]),
    lambda: VoltageMeasurementErrors(source="hidden"),
    lambda: FrameErrors(np.inf), lambda: TimingErrors(2), lambda: TimingErrors(True),
    lambda: ActuationErrors(bus_sag_fraction=1), lambda: ActuationErrors(-.1),
    lambda: OperatingDrift(0), lambda: DriveNonidealities(current={}),
])
def test_invalid_configs(factory):
    with pytest.raises(ValueError, match="nonideality."):
        factory()


def test_immutable_nested_configs():
    with pytest.raises(FrozenInstanceError):
        IDEAL.frame.electrical_angle_bias_rad = .1
    assert IDEAL.is_ideal and not IDEAL.has_signal_errors
    assert not replace(IDEAL, drift=OperatingDrift(1.2)).has_signal_errors


def test_phase_chain_matches_explicit_transforms_and_quantization():
    cfg = replace(IDEAL, current=CurrentMeasurementErrors((1.03, .98, 1.01), (.01, -.02, .005), .002),
                  frame=FrameErrors(.04))
    dq, theta = np.array([[.2, .8], [-.4, 1.2]]), np.array([.3, 1.1])
    abc = np.array(inverse_clarke_transform(*inverse_park_transform(*dq.T, theta))).T
    adc = np.rint((abc*np.array(cfg.current.phase_gains)+cfg.current.phase_offsets_a)/.002)*.002
    expected = np.array(park_transform(*clarke_transform(*adc.T), theta+.04)).T
    np.testing.assert_array_equal(measure_current(dq, theta, cfg), expected)
    np.testing.assert_array_equal(quantize([.001, .003, -.003], .002), [0, .004, -.004])
    # Common phase offset is zero sequence, removed by amplitude-invariant Clarke.
    np.testing.assert_allclose(measure_current(dq, theta, replace(IDEAL,
        current=CurrentMeasurementErrors(phase_offsets_a=(.2, .2, .2)))), dq, atol=1e-15)


def test_frame_measurement_and_command_are_inverse_consistently():
    cfg = replace(IDEAL, frame=FrameErrors(.1))
    current = np.array([.7, 1.2])
    measured = measure_current(current, .8, cfg)
    command = apply_voltage(measured, current, .8, .9, 48, cfg)
    np.testing.assert_allclose((command.terminal_d_v, command.terminal_q_v), current, atol=1e-15)
    # Positive bias produces positive measured d from a true pure q vector.
    assert measure_current([0, 1], .8, cfg)[0] > 0


def test_voltage_sources_are_distinct_and_quantization_is_in_volts():
    cfg = replace(IDEAL, voltage=VoltageMeasurementErrors((1.1, .9), (.01, -.02), .01))
    np.testing.assert_allclose(estimator_voltage([1, 2], [-999, 999], cfg), [1.11, 1.78])
    sensed = replace(IDEAL, voltage=VoltageMeasurementErrors(source="terminal"), frame=FrameErrors(.1))
    np.testing.assert_allclose(estimator_voltage([999, 999], [0, 2], sensed),
                               [2*np.sin(.1), 2*np.cos(.1)])


def test_averaged_drop_opposes_current_and_bus_caps_actual_vector():
    cfg = replace(IDEAL, actuation=ActuationErrors(.1, .1))
    applied = apply_voltage([1, 0], [1, 0], 0, 0, 24, cfg)
    assert applied.terminal_d_v == pytest.approx(1-4*.1/3)
    assert applied.terminal_q_v == pytest.approx(0)
    zero = apply_voltage([0, 0], [0, 0], 0, 0, 24, cfg)
    assert zero.terminal_d_v == zero.terminal_q_v == 0  # sign(0)=0
    capped = apply_voltage([20, 10], [0, 0], 0, 0, 24, cfg)
    assert capped.bus_limited and capped.actual_bus_voltage_v == 21.6
    assert np.hypot(capped.terminal_d_v, capped.terminal_q_v) == pytest.approx(21.6/np.sqrt(3))
    assert capped.terminal_d_v/capped.terminal_q_v == pytest.approx(2)


def test_delay_first_hold_and_explicit_one_sample_alignment():
    values = np.arange(12).reshape(3, 4)
    np.testing.assert_array_equal(delayed_samples(values, 1), values[[0, 0, 1]])
    delay = FeedbackDelay(1)
    assert delay.sample(values[0]) == tuple(values[0])
    assert delay.sample(values[1]) == tuple(values[0])
    assert delay.sample(values[2]) == tuple(values[1])


def assert_record_equal(a, b):
    for field in fields(a):
        left, right = getattr(a, field.name), getattr(b, field.name)
        if isinstance(left, np.ndarray):
            np.testing.assert_array_equal(left, right)
        else:
            assert left == right


@pytest.mark.parametrize("provider,config", [
    (simulate_locked_rotor_measurements, ExcitationConfig(duration_s=.02)),
    (simulate_driven_rotor_measurements, RotatingExcitationConfig(duration_s=.02)),
])
def test_zero_errors_and_drift_only_preserve_electrical_records(provider, config):
    plant = PMSMParameters()
    baseline = provider(plant, config)
    assert_record_equal(baseline, provider(plant, config, IDEAL))
    assert_record_equal(baseline, provider(plant, config, replace(IDEAL, drift=OperatingDrift(1.5))))


def test_zero_errors_preserve_mechanical_records():
    plant = PMSMParameters()
    cfg = MechanicalExcitationConfig(iq_plateaus_a=(.2, 0), plateau_duration_s=.02)
    baseline = simulate_mechanical_measurements(plant, plant, cfg)
    zero = simulate_mechanical_measurements(plant, plant, cfg, IDEAL)
    assert_record_equal(baseline.measurements, zero.measurements)
    np.testing.assert_array_equal(baseline.applied_voltage_magnitude_v, zero.applied_voltage_magnitude_v)
    assert baseline.saturation_fraction == zero.saturation_fraction


def test_zero_errors_preserve_every_control_signal():
    kwargs = dict(simulation_time=.04, load_step_time=.02)
    baseline, zero = run_speed_foc_simulation(**kwargs), run_speed_foc_simulation(**kwargs, nonidealities=IDEAL)
    for key, value in baseline.items():
        if isinstance(value, np.ndarray):
            np.testing.assert_array_equal(value, zero[key], err_msg=key)


def test_operation_drift_isolated_from_controller_and_original_plant():
    plant = PMSMParameters()
    original = replace(plant)
    sim = run_speed_foc_simulation(plant_params=plant, controller_params=plant,
        simulation_time=.01, load_step_time=.005, nonidealities=replace(IDEAL, drift=OperatingDrift(1.5)))
    assert plant == original and sim["controller_params"] is plant
    assert sim["plant_params"].Rs == original.Rs*1.5
    for name in ("Ld", "Lq", "psi_f", "J", "B"):
        assert getattr(sim["plant_params"], name) == getattr(original, name)


def test_structured_errors_are_reproducible_and_not_noise_metadata():
    cfg = ExcitationConfig(duration_s=.02, current_noise_std_a=.01, voltage_noise_std_v=.02, seed=33)
    errors = replace(IDEAL, current=CurrentMeasurementErrors((1.15, 1.15, 1.15)),
                     voltage=VoltageMeasurementErrors((1.12, 1.12)))
    plant = PMSMParameters()
    a = simulate_locked_rotor_measurements(plant, cfg, errors)
    assert_record_equal(a, simulate_locked_rotor_measurements(plant, cfg, errors))
    clean = simulate_locked_rotor_measurements(plant, cfg)
    assert a.noise == clean.noise
    assert not np.array_equal(a.current_q_a, clean.current_q_a)


def test_sag_logging_actual_voltage_and_current_reference_frame():
    cfg = replace(IDEAL, actuation=ActuationErrors(.03, .1), frame=FrameErrors(.1), timing=TimingErrors(1))
    sim = run_speed_foc_simulation(simulation_time=.04, load_step_time=.02, dc_bus_voltage=6, nonidealities=cfg)
    assert sim["actual_dc_bus_voltage"] == 5.4 and sim["dc_bus_voltage"] == 6
    assert np.max(sim["voltage_magnitude"]) <= 5.4/np.sqrt(3)+1e-12
    assert np.any(sim["actual_bus_saturated"])
    assert np.any(sim["id_ref_true"] != 0)
    np.testing.assert_allclose(np.hypot(sim["id_ref_true"], sim["iq_ref_true"]), np.abs(sim["iq_ref"]), atol=1e-15)
    np.testing.assert_array_equal(sim["feedback_iq"][2:], sim["measured_iq"][:-2])


def test_predeclared_population_and_metrics_do_not_use_accuracy_for_control_success():
    from experiments.nonideality_robustness import scenarios, generate_motors, operation_metrics
    assert len(scenarios()) == 16 and len({c.name for c in scenarios()}) == 16
    assert list(generate_motors("development")) == list(generate_motors("development"))
    assert list(generate_motors("development"))[0][1] != list(generate_motors("evaluation"))[0][1]
    sim = run_speed_foc_simulation()
    # Reporting receives signals, not post-hoc parameter error labels.
    result = operation_metrics(sim)
    assert result["operation_status"] == "evaluated" and result["control_success"]
    assert result["terminal_command_discrepancy_rmse_v"] == 0


def test_existing_algorithm_contract_and_decision_apis():
    """Explicit M17 freeze guard; future redesign must review this contract."""
    from src.identification import estimate_standstill_parameters
    from src.rotating_identification import estimate_flux_linkage
    from src.mechanical_identification import estimate_mechanical_parameters
    from src.adaptive_commissioning import run_adaptive_commissioning
    from src.commissioning_quality import assess_commissioning
    from src.full_commissioning import complete_commissioning
    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root/"results/nonideality_robustness/baseline_algorithm_contract.json").read_text())
    for path, digest in contract["ast_sha256"].items():
        tree = ast.parse((root/path).read_text(encoding="utf-8"))
        tree.body = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     or n.name not in contract["excluded_provider_functions"]]
        # Python 3.12 introduced empty type_params fields; CI also runs 3.11.
        for node in ast.walk(tree):
            if hasattr(node, "type_params") and not node.type_params:
                node._fields = tuple(f for f in node._fields if f != "type_params")
        assert hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest() == digest, path
    for function in (estimate_standstill_parameters, estimate_flux_linkage,
                     estimate_mechanical_parameters, run_adaptive_commissioning,
                     assess_commissioning, complete_commissioning):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters.intersection({"plant", "plant_params", "truth", "accuracy", "control_success", "nonidealities"})


def test_development_gain_bias_is_accepted_without_inventing_confidence():
    from src.identification import estimate_standstill_parameters
    from src.rotating_identification import estimate_flux_linkage
    from src.commissioning_quality import assess_commissioning
    plant = PMSMParameters(Rs=.5, Ld=.001, Lq=.0012, psi_f=.022, J=.0005, B=.00015)
    ec = ExcitationConfig(current_noise_std_a=.01, voltage_noise_std_v=.01, speed_noise_std_rad_s=.02)
    rc = RotatingExcitationConfig(q_voltage_base_v=5, current_noise_std_a=.01, voltage_noise_std_v=.01, speed_noise_std_rad_s=.02)
    # A uniform current calibration error fits the SAME linear model, scaled.
    errors = replace(IDEAL, current=CurrentMeasurementErrors((1.15, 1.15, 1.15)))
    electrical = estimate_standstill_parameters(simulate_locked_rotor_measurements(plant, ec, errors))
    flux = estimate_flux_linkage(simulate_driven_rotor_measurements(plant, rc, errors), electrical, plant.pole_pairs)
    quality = assess_commissioning(electrical, flux, plant.pole_pairs)
    assert quality.accepted
    assert abs(electrical.Rs/plant.Rs-1) > .1
    assert electrical.Rs/plant.Rs == pytest.approx(1/1.15, abs=.002)


def test_development_negative_findings_are_retained_and_rejections_safe(monkeypatch):
    import csv
    from experiments.nonideality_robustness import generate_motors, commissioning_pair, scenarios, PRIOR
    root = Path(__file__).resolve().parents[1]
    with (root/"results/nonideality_robustness/development.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 192
    accepted_bad = [r for r in rows if r["exposure"] == "combined" and r["method"] == "adaptive"
                    and r["full_accepted"] == "True" and r["all_six_accurate"] == "False"]
    assert len(accepted_bad) == 6
    assert {r["scenario"] for r in accepted_bad} == {"current_strong", "voltage_strong", "inverter_strong"}
    _, plant, seed = next(generate_motors("development"))
    timing = next(c.errors for c in scenarios() if c.name == "timing_one_sample")
    import experiments.nonideality_robustness as experiment
    original = experiment.run_adaptive_commissioning
    captured = []
    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        captured.append(result)
        return result
    monkeypatch.setattr(experiment, "run_adaptive_commissioning", capture)
    pairs, history = commissioning_pair(plant, seed, timing)
    assert all(not row["full_accepted"] for row, _ in pairs)
    for row, result in pairs:
        if result is not None:
            assert result.retuned_controller_parameters(PRIOR) == PRIOR
    assert history[-1]["action"] == "model_residual_terminal"
    assert all(a["decision"] == "terminal" for a in history)
    assert not captured[0].controller_parameters_updated
    assert captured[0].controller_parameters == PRIOR
