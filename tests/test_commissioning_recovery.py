from dataclasses import replace

import numpy as np
import pytest

from experiments.commissioning_recovery import run_experiment
from src.foc import CurrentFOCController
from src.identification import (
    ExcitationConfig,
    estimate_standstill_parameters,
    simulate_locked_rotor_measurements,
)
from src.motor import PMSMParameters
from src.rotating_identification import (
    RotatingExcitationConfig,
    estimate_flux_linkage,
    simulate_driven_rotor_measurements,
)
from src.speed_control import SpeedController


@pytest.fixture(scope="module")
def electrical_estimate():
    plant = PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3)
    data = simulate_locked_rotor_measurements(
        plant, ExcitationConfig(current_noise_std_a=0.01, voltage_noise_std_v=0.01)
    )
    return estimate_standstill_parameters(data)


@pytest.mark.parametrize("flux", [0.015, 0.025, 0.035])
def test_flux_estimation_uses_noisy_rotating_measurements(electrical_estimate, flux):
    plant = PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=flux)
    data = simulate_driven_rotor_measurements(
        plant,
        RotatingExcitationConfig(
            q_voltage_base_v=5.0,
            current_noise_std_a=0.01,
            voltage_noise_std_v=0.01,
            speed_noise_std_rad_s=0.05,
        ),
    )
    estimate = estimate_flux_linkage(data, electrical_estimate, pole_pairs=4)

    assert not hasattr(data, "psi_f")
    assert estimate.psi_f == pytest.approx(flux, rel=0.02)
    assert estimate.convergence_psi_f[-1] == pytest.approx(estimate.psi_f)


def test_flux_estimator_rejects_zero_and_reversing_speed(electrical_estimate):
    data = simulate_driven_rotor_measurements(
        PMSMParameters(), RotatingExcitationConfig(duration_s=0.04)
    )
    stopped = replace(data, speed_rad_s=np.zeros_like(data.speed_rad_s))
    reversing = replace(data, speed_rad_s=np.linspace(-20.0, 20.0, len(data.speed_rad_s)))
    with pytest.raises(ValueError, match="nonzero"):
        estimate_flux_linkage(stopped, electrical_estimate, pole_pairs=4)
    with pytest.raises(ValueError, match="nonzero"):
        estimate_flux_linkage(reversing, electrical_estimate, pole_pairs=4)


@pytest.fixture(scope="module")
def recovery_case():
    return run_experiment()


def test_commissioning_updates_controller_assumptions_and_pi_gains(recovery_case):
    simulations = recovery_case["simulations"]
    plant = simulations["true-parameter reference"]["plant_params"]
    initial = simulations["mismatched"]["controller_params"]
    retuned = recovery_case["retuned_controller_params"]

    assert initial.psi_f != retuned.psi_f
    assert initial.Rs != retuned.Rs
    assert retuned.J == initial.J and retuned.B == initial.B
    assert simulations["self-commissioned"]["controller_params"] == retuned
    for name in ("Rs", "Ld", "Lq", "psi_f"):
        assert getattr(retuned, name) == pytest.approx(getattr(plant, name), rel=0.02)

    current_reference = CurrentFOCController(plant)
    current_retuned = CurrentFOCController(retuned)
    speed_reference = SpeedController(plant)
    speed_retuned = SpeedController(retuned)
    assert current_retuned.pi_d.kp == pytest.approx(current_reference.pi_d.kp, rel=0.02)
    assert current_retuned.pi_q.kp == pytest.approx(current_reference.pi_q.kp, rel=0.02)
    assert current_retuned.pi_q.ki == pytest.approx(current_reference.pi_q.ki, rel=0.02)
    assert speed_retuned.kp == pytest.approx(speed_reference.kp, rel=0.02)
    assert speed_retuned.ki == pytest.approx(speed_reference.ki, rel=0.02)


def test_retuning_recovers_post_load_performance_with_voltage_limit(recovery_case):
    metrics = {row["controller"]: row for row in recovery_case["performance"]}
    before = metrics["mismatched"]
    after = metrics["self-commissioned"]
    reference = metrics["true-parameter reference"]

    assert before["saturation_fraction"] > 0
    assert after["saturation_fraction"] > 0
    assert after["post_step_speed_rmse_rpm"] < 0.6 * before["post_step_speed_rmse_rpm"]
    assert after["post_step_iq_tracking_rmse_a"] < 0.6 * before["post_step_iq_tracking_rmse_a"]
    assert after["max_post_step_speed_deviation_rpm"] < before["max_post_step_speed_deviation_rpm"]
    assert after["post_step_speed_rmse_rpm"] == pytest.approx(
        reference["post_step_speed_rmse_rpm"], rel=0.02
    )
