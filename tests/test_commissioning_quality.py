from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from src.commissioning import CommissioningRejectedError, commission_from_measurements
from src.commissioning_quality import assess_commissioning
from src.identification import ExcitationConfig, estimate_standstill_parameters, simulate_locked_rotor_measurements
from src.identification_quality import MeasurementNoise, noise_information_fraction
from src.motor import PMSMParameters
from src.rotating_identification import RotatingExcitationConfig, RotatingMeasurements, simulate_driven_rotor_measurements
from src.speed_foc_simulation import run_speed_foc_simulation


@pytest.fixture(scope="module")
def good_data():
    plant = PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015)
    locked = simulate_locked_rotor_measurements(plant, ExcitationConfig(
        current_noise_std_a=0.01, voltage_noise_std_v=0.01, speed_noise_std_rad_s=0.02,
    ))
    rotating = simulate_driven_rotor_measurements(plant, RotatingExcitationConfig(
        q_voltage_base_v=5.0, current_noise_std_a=0.01,
        voltage_noise_std_v=0.01, speed_noise_std_rad_s=0.02,
    ))
    return locked, rotating


def test_quality_accepts_good_data_and_has_consistent_physical_diagnostics(good_data):
    result = commission_from_measurements(*good_data, known_pole_pairs=4)
    assert result.quality.accepted, result.quality.rejection_reasons
    assert result.retuned_controller_parameters(PMSMParameters()).Rs == result.electrical.Rs
    for estimate in (result.electrical, result.flux):
        d = estimate.diagnostics
        assert d.effective_rank == len(d.parameter_names)
        assert d.scaled_condition_number == pytest.approx(d.scaled_singular_values[0] / d.scaled_singular_values[-1])
        assert d.regressor_energy == pytest.approx(d.column_norms**2)
        assert d.parameter_standard_errors**2 == pytest.approx(np.diag(d.parameter_covariance))
        assert np.all(np.linalg.eigvalsh(d.parameter_covariance) >= -1e-20)
        for value in vars(d).values():
            if isinstance(value, (float, int, np.ndarray)):
                assert np.all(np.isfinite(value))


@pytest.mark.parametrize("kind", ["rank", "zero_speed", "low_speed", "missing_noise"])
def test_invalid_or_unassessable_data_returns_explicit_rejection(good_data, kind):
    locked, rotating = good_data
    if kind == "rank":
        locked = replace(locked, current_d_a=np.zeros_like(locked.current_d_a),
                         current_q_a=np.zeros_like(locked.current_q_a),
                         voltage_d_v=np.zeros_like(locked.voltage_d_v),
                         voltage_q_v=np.zeros_like(locked.voltage_q_v))
    elif kind in ("zero_speed", "low_speed"):
        rotating = replace(rotating, speed_rad_s=np.full_like(rotating.speed_rad_s,
                                                             0 if kind == "zero_speed" else 5))
    else:
        locked = replace(locked, noise=None)
    result = commission_from_measurements(locked, rotating, 4)
    assert not result.quality.accepted
    assert result.quality.rejection_reasons


@pytest.mark.parametrize("noise_a,scale", [(0.4, 1.0), (0.01, 0.01)])
def test_noisy_or_weak_information_is_rejected(good_data, noise_a, scale):
    plant = PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015)
    locked = simulate_locked_rotor_measurements(plant, ExcitationConfig(
        current_noise_std_a=noise_a, voltage_noise_std_v=0.01,
        d_voltage_v=1.2 * scale, q_voltage_v=1.4 * scale,
    ))
    result = commission_from_measurements(locked, good_data[1], 4)
    assert not result.quality.accepted
    assert "standstill.noise_information" in result.quality.rejection_reasons


@pytest.mark.parametrize("flux,accepted", [(0.025, True), (0.0001, False)])
def test_rotating_information_accepts_open_circuit_but_rejects_weak_back_emf(good_data, flux, accepted):
    # Constant nonzero speed is sufficient for the scalar flux regression;
    # demanding voltage variation here would incorrectly reject open-circuit data.
    data = RotatingMeasurements(
        time_s=np.arange(1001) * 1e-4, current_d_a=np.zeros(1001),
        current_q_a=np.zeros(1001), speed_rad_s=np.full(1001, 60.0),
        voltage_d_v=np.zeros(1000), voltage_q_v=np.full(1000, 4 * 60 * flux),
        noise=MeasurementNoise(0.01, 0.01, 0.02),
    )
    result = commission_from_measurements(good_data[0], data, 4)
    assert result.quality.accepted == accepted, result.quality.rejection_reasons
    if not accepted:
        assert "rotating.weak_back_emf" in result.quality.rejection_reasons


def test_rejected_result_cannot_retune_and_simulation_preserves_controller(good_data):
    bad_rotating = replace(good_data[1], speed_rad_s=np.zeros_like(good_data[1].speed_rad_s))
    result = commission_from_measurements(good_data[0], bad_rotating, 4)
    original = PMSMParameters(Rs=0.3, Ld=0.8e-3)
    with pytest.raises(CommissioningRejectedError, match="rejected"):
        result.retuned_controller_parameters(original)
    options = dict(controller_params=original, simulation_time=0.02, load_step_time=0.01)
    baseline = run_speed_foc_simulation(**options)
    fallback = run_speed_foc_simulation(**options, commissioning_result=result)
    assert fallback["controller_params"] is original
    assert not fallback["commissioning_accepted"]
    assert fallback["commissioning_rejection_reasons"] == result.quality.rejection_reasons
    np.testing.assert_array_equal(fallback["rpm"], baseline["rpm"])


def test_gate_operates_on_only_estimates_and_diagnostics(good_data):
    result = commission_from_measurements(*good_data, 4)
    # No plant object, errors, or control outcomes exist in these gate inputs.
    electrical = SimpleNamespace(**{name: getattr(result.electrical, name)
                                   for name in ("Rs", "Ld", "Lq", "diagnostics")})
    flux = SimpleNamespace(psi_f=result.flux.psi_f, diagnostics=result.flux.diagnostics)
    assert assess_commissioning(electrical, flux, 4).accepted
    assert not hasattr(good_data[0], "plant_params")
    assert not hasattr(good_data[1], "psi_f")


def test_noise_information_is_invariant_to_regressor_units():
    x = np.random.default_rng(1).normal(size=(100, 3))
    noise_energy = np.array([0.01, 0.02, 0.03])
    conversion = np.array([1e-3, 1e3, 10.0])
    assert noise_information_fraction(x, noise_energy) == pytest.approx(
        noise_information_fraction(x * conversion, noise_energy * conversion**2)
    )


def test_standstill_covariance_matches_independent_numerical_sensitivity():
    data = simulate_locked_rotor_measurements(PMSMParameters(), ExcitationConfig(duration_s=0.02))
    data = replace(data, noise=MeasurementNoise(current_std_a=0.01))
    fit = estimate_standstill_parameters(data)

    def fit_arrays(id_samples, iq_samples):
        x, y = [], []
        for k in range(0, 200, 10):
            d, q = id_samples[k:k+11], iq_samples[k:k+11]
            x.append([np.sum((d[:-1] + d[1:]) / 2) * 1e-4, d[-1] - d[0], 0])
            x.append([np.sum((q[:-1] + q[1:]) / 2) * 1e-4, 0, q[-1] - q[0]])
            y.extend([np.sum(data.voltage_d_v[k:k+10]) * 1e-4,
                      np.sum(data.voltage_q_v[k:k+10]) * 1e-4])
        return np.linalg.lstsq(np.asarray(x), y, rcond=None)[0]

    jacobians = []
    for axis in (0, 1):
        jacobian = np.zeros((3, 201))
        for k in range(201):
            plus = [data.current_d_a.copy(), data.current_q_a.copy()]
            minus = [data.current_d_a.copy(), data.current_q_a.copy()]
            plus[axis][k] += 1e-5
            minus[axis][k] -= 1e-5
            jacobian[:, k] = (fit_arrays(*plus) - fit_arrays(*minus)) / 2e-5
        jacobians.append(jacobian)
    expected = 0.01**2 * sum(j @ j.T for j in jacobians)
    np.testing.assert_allclose(fit.diagnostics.parameter_covariance, expected, rtol=1e-4, atol=1e-14)
