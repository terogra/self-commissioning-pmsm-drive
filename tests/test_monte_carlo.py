import csv
import json

import pytest

from experiments.commissioning_monte_carlo import save_results
from src.monte_carlo import (
    CommissioningCase,
    MonteCarloConfig,
    NoiseCondition,
    generate_cases,
    run_case,
    run_population,
    summarize_population,
)
from src.motor import PMSMParameters


def test_population_is_reproducible_and_covers_design_conditions():
    config = MonteCarloConfig(
        seed=123, repeats=2,
        noise_conditions=(NoiseCondition("low", 0.01, 0.01, 0.02),
                          NoiseCondition("high", 0.4, 0.2, 0.1)),
        commissioning_speeds_rpm=(150.0, 600.0),
        dc_bus_voltages_v=(12.0, 48.0),
        include_weak_excitation=False,
    )
    first = generate_cases(config)
    second = generate_cases(config)
    assert first == second
    assert len(first) == 16
    assert len({(c.noise.name, c.commissioning_speed_rpm, c.dc_bus_voltage_v)
                for c in first}) == 8
    assert len({(c.plant.Rs, c.plant.Ld, c.plant.Lq, c.plant.psi_f)
                for c in first}) == 16
    assert all(0.25 <= c.plant.Rs <= 0.75 and 0.012 <= c.plant.psi_f <= 0.036
               for c in first)


def test_small_population_keeps_failed_cases_and_aggregates_missing_values(tmp_path):
    config = MonteCarloConfig(
        seed=456, repeats=1,
        noise_conditions=(NoiseCondition("low", 0.01, 0.01, 0.02),),
        commissioning_speeds_rpm=(0.0, 600.0),
        dc_bus_voltages_v=(24.0,),
        include_weak_excitation=True,
    )
    rows = run_population(config)
    summary = summarize_population(rows)
    assert len(rows) == 3
    assert [row["status"] for row in rows] == [
        "estimator_failed", "completed", "estimator_failed"
    ]
    assert "100 rpm" in rows[0]["failure_reason"]
    assert "identify all three parameters" in rows[2]["failure_reason"]
    assert rows[0]["failure_stage"] == "rotating_excitation"
    assert rows[2]["failure_stage"] == "joint_identification"
    assert all(row["mismatched_speed_rmse_rpm"] is not None for row in rows)
    assert rows[0]["commissioned_speed_rmse_rpm"] is None
    assert rows[1]["commissioned_speed_rmse_rpm"] is not None
    assert summary["estimator_failure_count"] == 2
    assert summary["metrics"]["commissioned_speed_rmse_rpm"]["n_missing"] == 2
    assert summary["success_rate"] == summary["success_count"] / 3

    cases_path, summary_path, *figures = save_results(rows, summary, tmp_path)
    with cases_path.open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert len(saved) == 3
    assert saved[0]["status"] == "estimator_failed"
    assert saved[2]["status"] == "estimator_failed"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["total_cases"] == 3
    assert all(path.is_file() for path in figures)


def test_retuning_recovers_a_feasible_mismatched_case():
    plant = PMSMParameters(Rs=0.56, Ld=1.4e-3, Lq=0.8e-3, psi_f=0.015)
    case = CommissioningCase(
        case_id=0, plant=plant,
        noise=NoiseCondition("low", 0.01, 0.01, 0.02),
        commissioning_speed_rpm=600.0, dc_bus_voltage_v=24.0,
        excitation_scale=1.0, seed=17,
    )
    row = run_case(case)
    assert row["status"] == "completed"
    assert row["parameter_accurate"]
    assert row["workflow_success"]
    assert row["commissioned_speed_rmse_rpm"] < row["mismatched_speed_rmse_rpm"]
    assert row["commissioned_iq_tracking_rmse_a"] < row["mismatched_iq_tracking_rmse_a"]
    assert row["commissioned_recovery_time_s"] < row["mismatched_recovery_time_s"]
    assert row["commissioned_saturation_fraction"] >= 0
    for name in ("Rs", "Ld", "Lq", "psi_f"):
        assert row[f"estimate_{name}"] == pytest.approx(getattr(plant, name), rel=0.02)


def test_all_estimator_failures_still_produce_summary_and_plots(tmp_path):
    case = CommissioningCase(
        case_id=7, plant=PMSMParameters(),
        noise=NoiseCondition("low", 0.01, 0.01, 0.02),
        commissioning_speed_rpm=0.0, dc_bus_voltage_v=24.0,
        excitation_scale=1.0, seed=7,
    )
    rows = [run_case(case)]
    summary = summarize_population(rows)
    assert summary["success_rate"] == 0
    assert summary["metrics"]["absolute_error_psi_f_percent"]["n_available"] == 0
    assert summary["paired_metrics"]["speed_rmse_rpm"]["n_pairs"] == 0
    assert all(path.is_file() for path in save_results(rows, summary, tmp_path))
