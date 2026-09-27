from dataclasses import replace

import numpy as np
import pytest

from src.identification import (
    ExcitationConfig,
    StandstillMeasurements,
    estimate_standstill_parameters,
    predict_standstill_currents,
    simulate_locked_rotor_measurements,
)
from src.motor import PMSMParameters


@pytest.mark.parametrize(
    "plant",
    [
        PMSMParameters(Rs=0.24, Ld=0.6e-3, Lq=1.4e-3),
        PMSMParameters(Rs=0.40, Ld=1.0e-3, Lq=1.0e-3),
        PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3),
    ],
)
def test_identifies_distinct_electrical_plants_from_noisy_samples(plant):
    config = ExcitationConfig(
        current_noise_std_a=0.01,
        voltage_noise_std_v=0.01,
        speed_noise_std_rad_s=0.05,
    )
    samples = simulate_locked_rotor_measurements(plant, config)
    estimate = estimate_standstill_parameters(samples)
    predicted_d, predicted_q = predict_standstill_currents(samples, estimate)

    assert not hasattr(samples, "plant_params")
    for name in ("Rs", "Ld", "Lq"):
        assert getattr(estimate, name) == pytest.approx(getattr(plant, name), rel=0.02)
    assert np.sqrt(np.mean((samples.current_d_a - predicted_d) ** 2)) < 0.03
    assert np.sqrt(np.mean((samples.current_q_a - predicted_q) ** 2)) < 0.03
    assert estimate.convergence_time_s[-1] == pytest.approx(config.duration_s)


def test_unexcited_measurements_have_no_identifiable_parameters():
    time = np.arange(101) * 100e-6
    zeros_at_samples = np.zeros(101)
    zeros_on_intervals = np.zeros(100)
    samples = StandstillMeasurements(
        time_s=time,
        current_d_a=zeros_at_samples,
        current_q_a=zeros_at_samples,
        speed_rad_s=zeros_at_samples,
        voltage_d_v=zeros_on_intervals,
        voltage_q_v=zeros_on_intervals,
    )
    with pytest.raises(ValueError, match="Excitation"):
        estimate_standstill_parameters(samples)


def test_standstill_estimator_rejects_rotating_data():
    samples = simulate_locked_rotor_measurements(PMSMParameters(), ExcitationConfig(duration_s=0.04))
    rotating = replace(samples, speed_rad_s=np.full_like(samples.speed_rad_s, 2.0))
    with pytest.raises(ValueError, match="near-zero"):
        estimate_standstill_parameters(rotating)


def test_flux_linkage_does_not_affect_locked_rotor_electrical_data():
    config = ExcitationConfig(duration_s=0.04)
    low_flux = simulate_locked_rotor_measurements(PMSMParameters(psi_f=0.015), config)
    high_flux = simulate_locked_rotor_measurements(PMSMParameters(psi_f=0.035), config)

    assert low_flux.current_d_a == pytest.approx(high_flux.current_d_a)
    assert low_flux.current_q_a == pytest.approx(high_flux.current_q_a)


def test_commissioning_excitation_must_respect_dc_bus():
    with pytest.raises(ValueError, match="SVPWM"):
        simulate_locked_rotor_measurements(
            PMSMParameters(),
            ExcitationConfig(d_voltage_v=10.0, q_voltage_v=10.0, dc_bus_voltage_v=12.0),
        )
