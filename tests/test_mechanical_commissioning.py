from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.full_commissioning_recovery import run_experiment, save_results
from src.commissioning import CommissioningRejectedError
from src.commissioning_quality import CommissioningQuality
from src.full_commissioning import complete_commissioning
from src.identification_quality import MeasurementNoise
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.mechanical_identification import (
    MechanicalMeasurements, assess_mechanical, estimate_mechanical_parameters, reconstruct_torque,
)
from src.motor import PMSMModel, PMSMParameters
from src.speed_control import SpeedController
from src.speed_foc_simulation import run_speed_foc_simulation


@pytest.fixture(scope="module")
def comparison():
    return run_experiment()


@pytest.mark.parametrize("j,b", [(2e-4, 1e-4), (8e-4, 4e-4)])
def test_noisy_identification_on_multiple_mechanical_plants(comparison, j, b):
    e = comparison["full"].electrical
    plant = replace(comparison["simulations"]["oracle"]["plant_params"], J=j, B=b)
    assumed = e.retuned_controller_parameters(PMSMParameters())
    data = simulate_mechanical_measurements(plant, assumed).measurements
    full = complete_commissioning(e, data)
    assert full.quality.accepted, full.quality.rejection_reasons
    assert full.mechanical.estimate.J == pytest.approx(j, rel=0.02)
    assert full.mechanical.estimate.B == pytest.approx(b, rel=0.03)


def test_estimator_has_only_samples_and_electrical_inputs_no_hidden_torque(comparison, monkeypatch):
    data = comparison["record"].measurements
    e = comparison["full"].electrical
    # Destroy access to the plant torque method AFTER generating ordinary data.
    def forbidden(*args):
        raise AssertionError("hidden plant torque read by estimator")
    monkeypatch.setattr(PMSMModel, "electromagnetic_torque", forbidden)
    assert not hasattr(data, "J") and not hasattr(data, "B") and not hasattr(data, "torque")
    electrical = SimpleNamespace(Ld=e.electrical.Ld, Lq=e.electrical.Lq, diagnostics=e.electrical.diagnostics)
    flux = SimpleNamespace(psi_f=e.flux.psi_f, diagnostics=e.flux.diagnostics)
    fit = estimate_mechanical_parameters(data, electrical, flux, e.pole_pairs)
    assert assess_mechanical(fit).accepted
    # Multiplying the reconstructed electrical torque scales J/B: no oracle torque.
    scaled = estimate_mechanical_parameters(data, replace(e.electrical, Ld=2*e.electrical.Ld,
                                            Lq=2*e.electrical.Lq), replace(e.flux, psi_f=2*e.flux.psi_f), 4)
    assert scaled.J == pytest.approx(2*fit.J)
    assert scaled.B == pytest.approx(2*fit.B)


@pytest.mark.parametrize("kind", ["zero", "constant_speed", "unknown_load", "missing_noise", "noisy_speed", "weak", "bias_change"])
def test_rejects_bad_or_unassessable_records(comparison, kind):
    data = comparison["record"].measurements
    e = comparison["full"].electrical
    if kind == "zero":
        data = replace(data, speed_rad_s=np.zeros_like(data.speed_rad_s),
                       current_d_a=np.zeros_like(data.current_d_a), current_q_a=np.zeros_like(data.current_q_a))
    elif kind == "constant_speed":
        data = replace(data, speed_rad_s=np.ones_like(data.speed_rad_s)*20)
    elif kind == "unknown_load":
        data = replace(data, known_load_torque_nm=None)
    elif kind == "missing_noise":
        data = replace(data, noise=None)
    elif kind == "noisy_speed":
        data = replace(data, speed_rad_s=data.speed_rad_s + np.random.default_rng(12).normal(0, 3, len(data.time_s)),
                       noise=MeasurementNoise(current_std_a=0.01, speed_std_rad_s=3))
    elif kind == "weak":
        # Low signal with the same calibrated sensor noise: artificial measured
        # record used to exercise quality, not a hidden-parameter regression.
        rng = np.random.default_rng(91)
        data = replace(data, speed_rad_s=0.005*data.speed_rad_s + rng.normal(0, 0.05, len(data.time_s)),
                       current_q_a=0.005*data.current_q_a + rng.normal(0, 0.01, len(data.time_s)))
    else:
        iq = data.current_q_a.copy()
        iq[len(iq)//2:] += 0.3
        data = replace(data, current_q_a=iq)
    result = complete_commissioning(e, data)
    assert not result.quality.accepted
    assert result.mechanical.quality.rejection_reasons
    if kind in ("zero", "constant_speed"):
        assert "mechanical.rank_deficiency" in result.quality.rejection_reasons
    if kind == "bias_change":
        assert "mechanical.inconsistent_halves" in result.quality.rejection_reasons


def test_rejected_mechanics_cannot_update_speed_configuration(comparison):
    e = comparison["full"].electrical
    full = complete_commissioning(e, replace(comparison["record"].measurements, noise=None))
    prior = PMSMParameters(J=9e-4, B=8e-4)
    with pytest.raises(CommissioningRejectedError):
        full.retuned_controller_parameters(prior)
    kwargs = dict(controller_params=prior, simulation_time=0.02, load_step_time=0.01)
    before = run_speed_foc_simulation(**kwargs)
    after = run_speed_foc_simulation(**kwargs, commissioning_result=full)
    assert after["controller_params"] is prior
    np.testing.assert_array_equal(before["rpm"], after["rpm"])
    assert after["commissioning_accepted"] is False
    assert "mechanical.relative_uncertainty" in after["commissioning_rejection_reasons"]


@pytest.mark.parametrize("mode", ["weak_acceleration", "tiny_speed_range"])
def test_physical_information_checks_detect_axis_specific_weakness(comparison, mode):
    e = comparison["full"].electrical
    time = np.arange(2501)*0.001
    if mode == "weak_acceleration":
        speed = 30 + 0.001*np.sin(2*np.pi*time)
        acceleration = 0.001*2*np.pi*np.cos(2*np.pi*time)
    else:
        speed = 0.1*np.sin(2*np.pi*4*time)
        acceleration = 0.1*2*np.pi*4*np.cos(2*np.pi*4*time)
    # Analytic fixture supplies ordinary samples. No numerical differentiation
    # occurs in the estimator; calibrated noise tests sensitivity of this trace.
    iq = (5e-4*acceleration + 3e-4*speed)/(6*e.flux.psi_f)
    data = MechanicalMeasurements(time, np.zeros_like(time), iq, speed, 0.0, MeasurementNoise(0.01, 0, 0.05))
    full = complete_commissioning(e, data)
    assert full.mechanical.estimate is not None
    assert not full.quality.accepted
    assert "mechanical.insufficient_excitation" in full.quality.rejection_reasons
    if mode == "weak_acceleration":
        assert "mechanical.noise_information" in full.quality.rejection_reasons
    else:
        d = full.mechanical.estimate.diagnostics
        assert d.standard_error_bound[1]/full.mechanical.estimate.B > 0.10/3


def test_electrical_gate_cannot_be_bypassed(comparison):
    e = replace(comparison["full"].electrical, quality=CommissioningQuality(False, ("electrical_failed",)))
    full = complete_commissioning(e, comparison["record"].measurements)
    assert full.mechanical.estimate is None
    assert not full.quality.accepted
    assert "electrical_failed" in full.quality.rejection_reasons


def test_accepted_mechanics_retunes_speed_gains_and_electrical_only_preserves_prior(comparison):
    full = comparison["full"]
    prior = comparison["simulations"]["mismatched"]["controller_params"]
    fitted = full.retuned_controller_parameters(prior)
    electric_only = full.electrical.retuned_controller_parameters(prior)
    assert (electric_only.J, electric_only.B) == (prior.J, prior.B)
    assert (fitted.J, fitted.B) == (full.mechanical.estimate.J, full.mechanical.estimate.B)
    speed = SpeedController(fitted)
    omega_n = 2*np.pi*10
    assert speed.kp == pytest.approx((2*omega_n*fitted.J - fitted.B)/(1.5*4*fitted.psi_f))
    assert speed.ki == pytest.approx(omega_n**2*fitted.J/(1.5*4*fitted.psi_f))
    assert speed.ki != SpeedController(electric_only).ki


def test_full_recovery_approaches_oracle_and_improves_speed_beyond_electrical_only(comparison):
    metrics = {r["controller"]: r for r in comparison["performance"]}
    full, oracle, electrical = (metrics[n] for n in ("full commissioned", "oracle", "electrical-only"))
    assert full["post_step_speed_rmse_rpm"] < 0.5*electrical["post_step_speed_rmse_rpm"]
    assert full["max_post_step_speed_deviation_rpm"] < 0.6*electrical["max_post_step_speed_deviation_rpm"]
    assert full["startup_overshoot_rpm"] < electrical["startup_overshoot_rpm"]
    assert full["post_step_speed_rmse_rpm"] == pytest.approx(oracle["post_step_speed_rmse_rpm"], rel=0.01)
    assert full["post_step_iq_tracking_rmse_a"] == pytest.approx(oracle["post_step_iq_tracking_rmse_a"], rel=0.01)
    # The faster speed response need not improve every current metric.
    assert full["post_step_iq_tracking_rmse_a"] > electrical["post_step_iq_tracking_rmse_a"]


def test_diagnostics_and_generated_artifacts(comparison, tmp_path):
    estimate = comparison["full"].mechanical.estimate
    d = estimate.diagnostics
    assert d.effective_rank == 2
    assert d.scaled_condition_number == pytest.approx(d.scaled_singular_values[0]/d.scaled_singular_values[-1])
    assert d.regressor_energy == pytest.approx(d.column_norms**2)
    assert np.all(np.linalg.eigvalsh(d.sensor_covariance) >= -1e-20)
    assert d.standard_error_bound == pytest.approx(np.sqrt(np.diag(d.sensor_covariance)) + d.electrical_standard_error_bound)
    assert estimate.convergence_parameters[-1] == pytest.approx([estimate.J, estimate.B])
    for value in vars(d).values():
        if isinstance(value, (float, int, np.ndarray)):
            assert np.all(np.isfinite(value))
    save_results(comparison, tmp_path)
    assert len(list(tmp_path.iterdir())) == 6


def test_measurement_reproducibility_and_excitation_limits(comparison):
    e = comparison["full"].electrical
    plant = comparison["simulations"]["oracle"]["plant_params"]
    assumed = e.retuned_controller_parameters(PMSMParameters())
    config = MechanicalExcitationConfig(iq_plateaus_a=(0.8, 0.0), plateau_duration_s=0.1)
    first = simulate_mechanical_measurements(plant, assumed, config)
    second = simulate_mechanical_measurements(plant, assumed, config)
    np.testing.assert_array_equal(first.measurements.speed_rad_s, second.measurements.speed_rad_s)
    assert max(first.applied_voltage_magnitude_v) <= config.dc_bus_voltage_v / np.sqrt(3)
    with pytest.raises(ValueError, match="limit"):
        simulate_mechanical_measurements(plant, assumed, replace(config, iq_plateaus_a=(2.0,)))


def test_sensor_covariance_and_electrical_sensitivity_against_finite_differences(comparison):
    original = comparison["record"].measurements
    data = replace(original, **{name: getattr(original, name)[::5] for name in
                               ("time_s", "current_d_a", "current_q_a", "speed_rad_s")})
    e = comparison["full"].electrical
    fitted = estimate_mechanical_parameters(data, e.electrical, e.flux, 4, window_samples=10)
    arrays = [data.current_d_a, data.current_q_a, data.speed_rad_s]
    constants = np.array([e.electrical.Ld, e.electrical.Lq, e.flux.psi_f])

    def fit(samples, parameters):
        d, q, speed = samples
        ld, lq, psi = parameters
        def area(x):
            return 0.005 * ((x[:-1]+x[1:])/2).reshape(-1, 10).sum(axis=1)
        x = np.column_stack((speed[10::10]-speed[:-10:10], area(speed)))
        return np.linalg.lstsq(x, area(6*(psi*q + (ld-lq)*d*q)), rcond=None)[0]

    covariance = np.zeros((2, 2))
    for axis, std in enumerate((data.noise.current_std_a, data.noise.current_std_a, data.noise.speed_std_rad_s)):
        jac = np.zeros((2, len(data.time_s)))
        for k in range(len(data.time_s)):
            plus, minus = [a.copy() for a in arrays], [a.copy() for a in arrays]
            plus[axis][k] += 1e-5
            minus[axis][k] -= 1e-5
            jac[:, k] = (fit(plus, constants)-fit(minus, constants))/2e-5
        covariance += std**2 * (jac @ jac.T)
    np.testing.assert_allclose(fitted.diagnostics.sensor_covariance, covariance, rtol=1e-5, atol=1e-18)
    for k in range(3):
        plus, minus = constants.copy(), constants.copy()
        plus[k] += 1e-7
        minus[k] -= 1e-7
        derivative = (fit(arrays, plus)-fit(arrays, minus))/2e-7
        np.testing.assert_allclose(fitted.diagnostics.electrical_sensitivity[:, k], derivative, rtol=1e-4, atol=1e-10)


def test_population_seeds_and_mechanics_are_reproducible_and_separate():
    from experiments.mechanical_population import generate_mechanical_cases
    development = generate_mechanical_cases("development")
    assert development == generate_mechanical_cases("development")
    evaluation = generate_mechanical_cases("evaluation")
    # All three sensor streams (mechanical, standstill, rotating) are disjoint.
    dev_seeds = {c.seed+k for c in development for k in (0, 1, 2)}
    eval_seeds = {c.seed+k for c in evaluation for k in (0, 1, 2)}
    assert dev_seeds.isdisjoint(eval_seeds)
    assert len({c.plant.J for c in development}) == len(development)
    assert all(1.5e-4 <= c.plant.J <= 9e-4 and 0.5e-4 <= c.plant.B <= 5e-4 for c in evaluation)


def test_small_population_preserves_success_and_rank_failure(comparison, monkeypatch, tmp_path):
    import experiments.mechanical_population as population
    from src.monte_carlo import CommissioningCase, NoiseCondition
    plant = comparison["simulations"]["oracle"]["plant_params"]
    good = CommissioningCase(0, plant, NoiseCondition("low", 0.01, 0, 0.05), 600, 24, 1.0, 1101)
    bad = replace(good, case_id=1, excitation_scale=0.0, noise=NoiseCondition("none", 0, 0, 0), seed=2101)
    monkeypatch.setattr(population, "generate_mechanical_cases", lambda _: [good, bad])
    rows = population.run_population("development")
    assert [r["status"] for r in rows] == ["accepted", "estimator_failed"]
    assert not rows[1]["full_accepted"]
    # Explicit fallback metrics are retained but never scored as accepted control.
    assert rows[1]["full commissioned_post_step_speed_rmse_rpm"] == rows[1]["mismatched_post_step_speed_rmse_rpm"]
    summary = population.save_results(rows, "development", tmp_path)
    assert summary["total_cases"] == 2
    assert summary["coverage"] == 0.5
    assert summary["parameter_errors"]["all"]["J"]["n_missing"] == 1
