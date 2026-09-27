from dataclasses import replace

import numpy as np
import pytest

from experiments.parameter_sensitivity import (
    MISMATCH_PERCENTS,
    PARAMETERS,
    calculate_metrics,
    run_sweep,
)
from src.motor import PMSMParameters
from src.speed_foc_simulation import run_speed_foc_simulation


def test_nominal_speed_loop_and_independent_default_parameters():
    result = run_speed_foc_simulation()

    assert result["plant_params"] is not result["controller_params"]
    assert result["plant_params"] == result["controller_params"]
    assert result["rpm"][-1] == pytest.approx(1000.0, abs=0.1)
    assert np.max(np.abs(result["iq"][-1000:] - result["iq_ref"][-1000:])) < 0.01
    assert np.any(result["load_torque"] == 0.05)
    assert np.any(result["load_torque"] == 0.0)


@pytest.mark.parametrize("parameter", PARAMETERS)
def test_plant_and_controller_parameters_can_change_independently(parameter):
    nominal = PMSMParameters()
    options = {"simulation_time": 0.08, "load_step_time": 0.04}
    baseline = run_speed_foc_simulation(nominal, replace(nominal), **options)
    mismatch = {parameter: getattr(nominal, parameter) * 0.6}
    different_plant = run_speed_foc_simulation(
        replace(nominal, **mismatch), replace(nominal), **options
    )
    different_controller = run_speed_foc_simulation(
        replace(nominal), replace(nominal, **mismatch), **options
    )

    assert different_plant["controller_params"] == baseline["controller_params"]
    assert different_controller["plant_params"] == baseline["plant_params"]
    assert np.max(np.abs(different_plant["rpm"] - baseline["rpm"])) > 1e-6
    assert np.max(np.abs(different_controller["rpm"] - baseline["rpm"])) > 1e-6


def test_sweep_covers_one_parameter_at_a_time_with_fixed_controller():
    nominal = PMSMParameters()
    results = run_sweep(nominal, simulation_time=0.04, load_step_time=0.02)

    assert len(results) == 1 + len(PARAMETERS) * len(MISMATCH_PERCENTS)
    assert (results[0]["parameter"], results[0]["mismatch_pct"]) == ("nominal", 0)
    for row in results:
        sim = row["simulation"]
        assert sim["controller_params"] == nominal
        assert sim["controller_params"] is not sim["plant_params"]
        if row["parameter"] != "nominal":
            changed = [
                name for name in PARAMETERS
                if getattr(sim["plant_params"], name) != getattr(nominal, name)
            ]
            assert changed == [row["parameter"]]
            assert row["plant_value"] == pytest.approx(
                row["controller_value"] * (1 + row["mismatch_pct"] / 100)
            )


def test_metrics_measure_load_response_and_unrecovered_case():
    simulation = {
        "time": np.array([0.0, 0.1, 0.2, 0.3, 0.4]),
        "rpm": np.array([1000.0, 990.0, 980.0, 995.0, 1000.0]),
        "iq": np.array([0.0, 1.0, 1.0, 1.0, 1.0]),
        "iq_ref": np.ones(5),
        "speed_ref_rpm": 1000.0,
        "load_step_time": 0.1,
    }
    metrics = calculate_metrics(simulation)
    assert metrics["speed_rmse_rpm"] == pytest.approx(np.sqrt(525 / 5))
    assert metrics["iq_tracking_rmse_a"] == pytest.approx(np.sqrt(1 / 5))
    assert metrics["max_post_step_speed_deviation_rpm"] == pytest.approx(20.0)
    assert metrics["disturbance_recovery_time_s"] == pytest.approx(0.2)

    simulation["rpm"][-1] = 980.0
    assert np.isnan(calculate_metrics(simulation)["disturbance_recovery_time_s"])
