import numpy as np
import pytest

from experiments.voltage_saturation_mismatch import run_experiment
from src.foc import CurrentFOCController
from src.motor import PMSMParameters
from src.speed_foc_simulation import run_speed_foc_simulation


def test_voltage_vector_is_scaled_to_svpwm_circle():
    params = PMSMParameters()
    limited = CurrentFOCController(params, dc_bus_voltage=12.0)
    unlimited = CurrentFOCController(params, dc_bus_voltage=None)
    inputs = dict(id_ref=8.0, iq_ref=12.0, i_d=0.0, i_q=0.0, omega_m=0.0, dt=20e-6)

    applied = np.array(limited.update(**inputs))
    requested = np.array(unlimited.update(**inputs))
    limit = 12.0 / np.sqrt(3.0)

    assert limited.voltage_saturated
    assert np.linalg.norm(applied) == pytest.approx(limit)
    assert np.linalg.norm(requested) > limit
    assert applied == pytest.approx(requested * limit / np.linalg.norm(requested))
    assert limited.pi_d.integral < unlimited.pi_d.integral
    assert limited.pi_q.integral < unlimited.pi_q.integral


def test_anti_windup_recovers_after_sustained_voltage_saturation():
    params = PMSMParameters()
    dt = 20e-6

    def current_step(anti_windup_gain):
        controller = CurrentFOCController(
            params, dc_bus_voltage=3.0, anti_windup_gain=anti_windup_gain
        )
        iq = 0.0
        integral_at_step = None
        for k in range(2400):
            iq_ref = 5.0 if k < 2000 else 0.0
            _, vq = controller.update(0.0, iq_ref, 0.0, iq, 0.0, dt)
            iq += dt * (vq - params.Rs * iq) / params.Lq
            if k == 1999:
                integral_at_step = controller.pi_q.integral
        return iq, integral_at_step

    recovered_iq, protected_integral = current_step(None)
    wound_up_iq, unprotected_integral = current_step(0.0)

    assert abs(protected_integral) < abs(unprotected_integral)
    assert abs(recovered_iq) < 0.1
    assert wound_up_iq > 1.0


def test_speed_simulation_logs_applied_voltage_and_saturation():
    limited = run_speed_foc_simulation(
        dc_bus_voltage=6.0, simulation_time=0.08, load_step_time=0.04
    )
    limit = 6.0 / np.sqrt(3.0)

    assert limited["voltage_limit"] == pytest.approx(limit)
    assert np.any(limited["voltage_saturated"])
    assert np.all(limited["voltage_magnitude"] <= limit + 1e-12)
    assert limited["voltage_magnitude"] == pytest.approx(
        np.hypot(limited["voltage_d"], limited["voltage_q"])
    )
    assert np.array_equal(
        limited["voltage_saturated"],
        limited["requested_voltage_magnitude"] > limit,
    )


def test_nominal_48v_bus_keeps_original_trajectory():
    constrained = run_speed_foc_simulation()
    unconstrained = run_speed_foc_simulation(dc_bus_voltage=None)

    assert not np.any(constrained["voltage_saturated"])
    assert constrained["rpm"] == pytest.approx(unconstrained["rpm"])
    assert constrained["iq"] == pytest.approx(unconstrained["iq"])


def test_flux_mismatch_becomes_voltage_limited_at_24v():
    rows = run_experiment()
    cases = {(row["psi_f_mismatch_pct"], row["voltage_mode"]): row for row in rows}

    assert cases[(0, "limited")]["saturation_fraction"] == 0.0
    assert cases[(40, "limited")]["saturation_fraction"] > 0.5
    assert cases[(40, "limited")]["final_speed_rpm"] < 960.0
    assert cases[(40, "unconstrained")]["final_speed_rpm"] > 990.0


@pytest.mark.parametrize("bus_voltage", [0.0, -1.0, float("nan")])
def test_bus_voltage_must_be_physically_valid(bus_voltage):
    with pytest.raises(ValueError):
        CurrentFOCController(PMSMParameters(), dc_bus_voltage=bus_voltage)
