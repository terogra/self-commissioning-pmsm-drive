"""Compile the actual C kernel and replay full state trajectories, not mocks."""

import ctypes as ct
from dataclasses import asdict, replace
import hashlib
import os
import re

import numpy as np
import pytest

from experiments.firmware_parity import commissioned_example, compile_c_tests
from firmware.parity import (
    ROOT, FLAGS, TOLERANCES, Abc, AlphaBeta, Dq, CurrentInput, CurrentOutput,
    CurrentState, PiConfig, PiState, SpeedConfig, SpeedState, VoltageOutput,
    c_configs, compile_core, compiler_path, f32, native_foc_step, ok, run_parity,
)
from src.commissioning import CommissioningRejectedError
from src.commissioning_quality import CommissioningQuality
from src.firmware_config import build_firmware_config, export_c_header
from src.foc import CurrentFOCController
from src.speed_control import SpeedController


@pytest.fixture(scope="module")
def commissioning():
    return commissioned_example()


@pytest.fixture(scope="module")
def config(commissioning):
    return build_firmware_config(commissioning[0], dc_bus_voltage_v=24)


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    compiler = compiler_path()
    if compiler is None:
        if os.environ.get("CI"):
            pytest.fail("CI must compile and exercise the C core with GCC/Clang")
        pytest.skip("Native C verification requires GCC/Clang; set PMSM_CC. Python-only tests still run.")
    core, build = compile_core(tmp_path_factory.mktemp("native-core"), compiler)
    yield core, build
    core.close()


@pytest.fixture(scope="module")
def replay(native, commissioning):
    return run_parity(native[0], *commissioning)


def test_strict_native_build_and_real_float(native):
    assert native[1]["flags"] == list(FLAGS)
    assert set(("-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic")) <= set(FLAGS)
    assert "-ffast-math" not in FLAGS
    assert ct.sizeof(ct.c_float) == 4
    assert native[1]["compiler"]


@pytest.mark.parametrize("stream", ["clarke", "inverse_clarke", "park", "inverse_park"])
def test_transforms_parity(replay, stream):
    rows = [r for r in replay[1] if r["stream"] == stream]
    assert len(rows) == (48 if "park" in stream else 6)
    assert any(r["input_0"] == 0 for r in rows)
    assert any(r["input_0"] < 0 for r in rows)
    for row in rows:
        for signal, error in row.items():
            if signal.startswith("error_"):
                assert error <= TOLERANCES["transforms"][0] + TOLERANCES["transforms"][1]*abs(row["python_"+signal[6:]])


@pytest.mark.parametrize("stream", ["pi_free", "pi_limited"])
def test_pi_full_trajectory_saturation_recovery_and_tracking(replay, stream):
    rows = [r for r in replay[1] if r["stream"] == stream]
    assert len(rows) == 128
    assert len([r for r in rows if r["tracking"]]) == 16
    if stream == "pi_limited":
        assert any(r["python_output"] == .75 == r["c_output"] for r in rows)
        assert any(r["python_output"] == -.75 == r["c_output"] for r in rows)
        assert any(abs(r["c_output"]) < .75 and r["sample"] >= 56 for r in rows)
    assert max(r["error_output"] for r in rows) < 2e-4
    assert max(r["error_integral"] for r in rows) < 2e-4


@pytest.mark.parametrize("bus", [48.0, 6.0, None])
def test_foc_requested_applied_and_backcalculation_trajectories(replay, bus):
    rows = [r for r in replay[1] if r["stream"] == f"foc_bus_{bus}"]
    assert len(rows) == 256
    assert {r["omega_m"] for r in rows} == {0, 20, 400, -300}
    assert any(r["id"] != 0 and r["iq"] != 0 for r in rows)
    for row in rows:
        assert all(np.isfinite(row["c_"+signal]) for signal in (
            "vd_requested", "vq_requested", "vd", "vq", "requested_magnitude", "magnitude", "d_integral", "q_integral"))
    if bus is None:
        assert not any(r["c_saturated"] for r in rows)
        assert all(r["c_vd"] == r["c_vd_requested"] and r["c_vq"] == r["c_vq_requested"] for r in rows)
    else:
        assert any(r["c_saturated"] for r in rows)
        assert any(not r["c_saturated"] for r in rows)
        for row in rows:
            assert row["c_magnitude"] <= bus/np.sqrt(3) + 8e-6
            if row["c_saturated"]:
                cross = row["c_vd"]*row["c_vq_requested"] - row["c_vq"]*row["c_vd_requested"]
                assert abs(cross) <= 2e-6*max(1, abs(row["c_vd"]*row["c_vq_requested"]))


def test_speed_limits_normal_recovery_and_entire_state(replay):
    rows = [r for r in replay[1] if r["stream"] == "speed"]
    assert len(rows) == 256
    assert all(r["c_iq_ref"] == 5 and r["c_integral"] == 0 for r in rows[:64])
    assert all(r["c_iq_ref"] == -5 and r["c_integral"] == 0 for r in rows[64:128])
    assert any(abs(r["c_iq_ref"]) < 5 and r["c_integral"] != 0 for r in rows[128:])


def test_combined_trace_compares_every_step_and_retains_maxima(replay):
    summary, _, trace = replay
    assert summary["total_compared_samples"] == 31484
    assert summary["sample_counts"] == dict(transforms=108, pi=256, foc=864, speed=256, combined=30000)
    assert summary["trace_artifact"]["compared_all_steps"] == 30000
    retained = {r["sample"] for r in trace}
    assert all(m["worst_sample"] in retained for m in summary["metrics"]["combined"].values())
    assert all(m["worst_relative_sample"] in retained for m in summary["metrics"]["combined"].values()
               if "worst_relative_sample" in m)
    for row in trace:
        # The serialized input stream itself is exactly representable on BOTH sides.
        for key in ("id_ref", "iq_reference_input", "id", "iq", "omega_m", "omega_ref", "dt"):
            assert f32(row[key]) == row[key]
    assert summary["worst_absolute"]["max_absolute_error"] <= 5e-3


def test_boundary_flag_differences_are_retained_not_hidden(replay):
    summary, vectors, _ = replay
    flags = summary["saturation_flags"]
    assert flags["nonboundary_agreements"] == flags["nonboundary_comparisons"]
    probes = [p for p in flags["boundary_probes"] if p["stream"] == "boundary"]
    rows = [r for r in vectors if r["stream"] == "boundary"]
    assert len(probes) == len(rows) == 96
    assert sum(not r["agree"] for r in flags["boundary_probes"]) == flags["total"] - flags["agreements"]
    # Counts of last-bit libm differences are platform-dependent; do not freeze 16.
    for probe, row in zip(probes, rows):
        assert probe["reference_flag"] == row["python_saturated"]
        assert probe["c_flag"] == row["c_saturated"]
        assert probe["distance_v"] <= probe["boundary_rounding_envelope_v"]


def test_secondary_float32_is_diagnostic_not_primary(replay):
    summary = replay[0]
    assert set(summary["secondary_binary32_foc_max_absolute_errors"]) == {
        "vd_requested", "vq_requested", "vd", "vq", "d_integral", "q_integral"}
    assert all(e <= 5e-3 for e in summary["secondary_binary32_foc_max_absolute_errors"].values())
    assert summary["metrics"]["combined"]["q_integral"]["max_absolute_error"] > 0


def test_frozen_budgets_match_protocol():
    protocol = (ROOT/"docs/firmware_core_protocol.md").read_text(encoding="utf-8")
    assert TOLERANCES == dict(transforms=(8e-6, 2e-6), pi=(2e-4, 2e-5), speed=(2e-4, 2e-5),
                              foc=(5e-3, 2e-5), combined=(5e-3, 2e-5))
    assert "Do not loosen these budgets" in protocol
    assert "16*u*" in protocol


def test_generated_header_compiles_and_c_assertions_run(native, config, tmp_path):
    export_c_header(config, tmp_path/"generated_motor_config.h", provenance="Simulated accepted full commissioning")
    result = compile_c_tests(tmp_path, tmp_path, compiler_path())
    assert re.fullmatch(r"43 C core checks passed", result)


@pytest.mark.parametrize("dt", [0, -1, np.nan, np.inf])
def test_invalid_dt_is_transactional(native, config, dt):
    core = native[0]
    motor, current, speed = c_configs(config)
    cs, ss = CurrentState(), SpeedState()
    cs.d_pi.integral, cs.q_pi.integral, ss.pi.integral = .25, -.5, .125
    out = CurrentOutput(1, 2, 3, 4, 5, 6, 1)
    iq = ct.c_float(17)
    before = bytes(cs), bytes(out), bytes(ss)
    inp = CurrentInput(0, 1, 0, 0, 20, dt)
    assert core.lib.pmsm_current_update(ct.byref(motor), ct.byref(current), ct.byref(cs), ct.byref(inp), ct.byref(out)) == 1
    assert core.lib.pmsm_speed_update(ct.byref(speed), ct.byref(ss), 1, 0, dt, ct.byref(iq)) == 1
    assert before == (bytes(cs), bytes(out), bytes(ss)) and iq.value == 17


@pytest.mark.parametrize("bad", ["bus", "limit", "gain", "motor", "pole_pairs", "flag"])
def test_invalid_current_configuration_cannot_initialize(native, config, bad):
    motor, current, _ = c_configs(config)
    if bad == "bus": current.dc_bus_voltage = -24
    elif bad == "limit": current.voltage_limit *= 2
    elif bad == "gain": current.anti_windup_gain = -1
    elif bad == "motor": motor.Ld = np.nan
    elif bad == "pole_pairs": motor.pole_pairs = 0
    else: current.voltage_limit_enabled = 2
    state = CurrentState(PiState(.25), PiState(.5))
    before = bytes(state)
    assert native[0].lib.pmsm_current_init(ct.byref(motor), ct.byref(current), ct.byref(state)) == 1
    assert bytes(state) == before


def test_foc_reset_is_deterministic_and_instances_are_independent(native, config):
    core = native[0]
    motor, current, _ = c_configs(config)
    a, b = CurrentState(), CurrentState()
    inp = tuple(map(f32, (.3, 4, -.1, .7, 400, 20e-6)))
    first = native_foc_step(core, motor, current, a, inp)
    untouched = bytes(b)
    for _ in range(20): native_foc_step(core, motor, current, a, inp)
    assert bytes(b) == untouched
    assert native_foc_step(core, motor, current, b, inp) == first
    core.lib.pmsm_current_reset(ct.byref(a))
    assert a.d_pi.integral == a.q_pi.integral == 0
    assert native_foc_step(core, motor, current, a, inp) == first


def test_overflow_does_not_partially_commit_foc_or_speed(native, config):
    motor, current, speed = c_configs(config)
    state = CurrentState(PiState(.25), PiState(.5))
    output = CurrentOutput(1, 2, 3, 4, 5, 6, 1)
    before = bytes(state), bytes(output)
    huge = float(np.finfo(np.float32).max)
    # d update would succeed; q arithmetic overflows. Neither may be committed.
    inp = CurrentInput(0, huge, 0, -huge, 20, 20e-6)
    assert native[0].lib.pmsm_current_update(ct.byref(motor), ct.byref(current), ct.byref(state), ct.byref(inp), ct.byref(output)) == 2
    assert before == (bytes(state), bytes(output))
    ss, iq = SpeedState(PiState(.5)), ct.c_float(7)
    assert native[0].lib.pmsm_speed_update(ct.byref(speed), ct.byref(ss), huge, -huge, 20e-6, ct.byref(iq)) == 2
    assert ss.pi.integral == .5 and iq.value == 7


def test_zero_aw_gain_and_negative_speed_kp_preserve_python_semantics(native, config, commissioning):
    motor, current, _ = c_configs(config)
    current.anti_windup_gain = 0
    state = CurrentState()
    inp = tuple(map(f32, (1, 10, 0, 0, 400, 20e-6)))
    actual, saturated = native_foc_step(native[0], motor, current, state, inp)
    assert saturated
    assert actual["d_integral"] == pytest.approx(current.ki_d*inp[0]*inp[-1], rel=2e-6)
    assert actual["q_integral"] == pytest.approx(current.ki_q*inp[1]*inp[-1], rel=2e-6)
    # Existing speed formula can produce negative Kp. C must not silently reject it.
    parameters = commissioning[1]
    python = SpeedController(parameters, damping_ratio=0)
    cfg = SpeedConfig(f32(python.kp), f32(python.ki), 5, f32(python.kt))
    assert cfg.kp < 0
    ss, out = SpeedState(), ct.c_float()
    ok(native[0].lib.pmsm_speed_init(ct.byref(cfg), ct.byref(ss)))
    ok(native[0].lib.pmsm_speed_update(ct.byref(cfg), ct.byref(ss), 1, 0, f32(.001), ct.byref(out)))
    assert out.value == pytest.approx(python.update(1, 0, f32(.001)), abs=2e-4, rel=2e-5)


@pytest.mark.parametrize("enabled", [0, 1])
def test_nonfinite_voltage_limit_is_rejected_without_output_change(native, enabled):
    output = VoltageOutput(1, 2, 3, 4, 1)
    before = bytes(output)
    assert native[0].lib.pmsm_limit_voltage(1, 2, enabled, np.nan, ct.byref(output)) == 1
    assert bytes(output) == before


@pytest.mark.parametrize("bus", [24, None])
def test_accepted_config_gains_match_existing_constructors(commissioning, bus):
    full, parameters, _ = commissioning
    config = build_firmware_config(full, dc_bus_voltage_v=bus)
    current = CurrentFOCController(parameters, dc_bus_voltage=bus)
    speed = SpeedController(parameters)
    assert asdict(config.motor) == {n: (v if n == "pole_pairs" else f32(v)) for n, v in vars(parameters).items()}
    assert (config.current.kp_d, config.current.ki_d, config.current.kp_q, config.current.ki_q) == tuple(map(f32,
        (current.pi_d.kp, current.pi_d.ki, current.pi_q.kp, current.pi_q.ki)))
    assert config.current.anti_windup_gain == f32(current.anti_windup_gain)
    assert (config.speed.kp, config.speed.ki, config.speed.torque_constant) == tuple(map(f32, (speed.kp, speed.ki, speed.kt)))
    assert config.current.voltage_limit_enabled == int(bus is not None)
    assert config.current.voltage_limit == (0 if bus is None else f32(current.voltage_limit))


@pytest.mark.parametrize("stage", ["electrical", "mechanical"])
def test_rejection_blocks_config_and_header(commissioning, tmp_path, stage):
    full = commissioning[0]
    rejected = replace(getattr(full, stage), quality=CommissioningQuality(False, (stage+".test_rejection",)))
    result = replace(full, **{stage: rejected})
    path = tmp_path/"must_not_exist.h"
    with pytest.raises(CommissioningRejectedError):
        export_c_header(build_firmware_config(result), path)
    assert not path.exists()


def test_only_full_result_is_accepted_by_builder(commissioning):
    for invalid in (commissioning[0].electrical, commissioning[2], None):
        with pytest.raises(TypeError, match="requires_full"):
            build_firmware_config(invalid)


@pytest.mark.parametrize("setting", [dict(current_bandwidth_hz=0), dict(natural_frequency_hz=np.nan),
    dict(iq_limit_a=-1), dict(dc_bus_voltage_v=0), dict(anti_windup_gain=-1), dict(damping_ratio=-1)])
def test_exporter_rejects_invalid_tuning(commissioning, setting):
    with pytest.raises(ValueError): build_firmware_config(commissioning[0], **setting)


@pytest.mark.parametrize("kind", ["nan", "underflow", "inconsistent_limit", "bad_prefix"])
def test_header_refuses_invalid_or_unrepresentable_config(config, tmp_path, kind):
    if kind == "nan": config = replace(config, motor=replace(config.motor, Rs=np.nan))
    elif kind == "underflow": config = replace(config, motor=replace(config.motor, Ld=1e-60))
    elif kind == "inconsistent_limit": config = replace(config, current=replace(config.current, voltage_limit=1))
    path = tmp_path/"invalid.h"
    with pytest.raises(ValueError): export_c_header(config, path, prefix="bad-name" if kind == "bad_prefix" else "commissioned")
    assert not path.exists()


def test_exporter_is_deterministic_and_does_not_use_oracle(config, tmp_path):
    a = export_c_header(config, tmp_path/"a.h", provenance="Simulated accepted full commissioning")
    b = export_c_header(config, tmp_path/"b.h", provenance="Simulated accepted full commissioning")
    assert a.read_bytes() == b.read_bytes()
    assert "Simulated accepted full commissioning" in a.read_text()
    code = (ROOT/"src/firmware_config.py").read_text(encoding="utf-8")
    assert "true_" not in code and "plant_params" not in code
    assert "CurrentFOCController(parameters" in code and "SpeedController(parameters" in code


def test_portable_core_has_no_heap_platform_or_double_dependencies():
    sources = list((ROOT/"firmware/src").glob("*.c")) + list((ROOT/"firmware/include").glob("*.h"))
    for path in sources:
        code = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
        assert not re.search(r"\b(malloc|calloc|realloc|free|double|PyObject|HAL_\w+|printf|fopen)\b", code)
        assert not re.search(r'#\s*include\s*[<"](?:Python|windows|pthread|unistd|stm32)', code, flags=re.I)
        # No file-scope object declarations; static functions are allowed.
        depth = 0
        for line in code.splitlines():
            if depth == 0:
                assert not re.match(r"\s*(?:static\s+)?(?:float|Pmsm\w+)\s+\w+\s*(?:=|\[)", line)
            depth += line.count("{") - line.count("}")
        assert depth == 0


@pytest.mark.parametrize("name,digest", [
    # Main's UTF-8 source hashes (newline normalized for Windows/Linux checkouts).
    ("controllers.py", "2d149864ea66e8e7410967d799c63f1b41b13305cca16018f2b673b48da34cce"),
    ("transforms.py", "d15adfed7d104669a2fafce8f8d45fd9d41a41ebd1a3aeb2c1449737da7841db"),
    ("foc.py", "57b2b0f5387212254fbee2895392808b7bf155abe7fd9304cc4f65e0359810a9"),
    ("speed_control.py", "3db4481023a224bc090671bae716be5f57ccb0b9f7e751af0ddd36b3d2d47368"),
])
def test_m18_does_not_change_python_reference(name, digest):
    assert hashlib.sha256((ROOT/"src"/name).read_text(encoding="utf-8").encode()).hexdigest() == digest
