"""Compile the C99 kernel and replay identical inputs against real Python controllers.

This host harness may use Python/ctypes/files/subprocess; none belongs to the
portable C runtime. Tolerances are declared in docs/firmware_core_protocol.md.
"""

import ctypes as ct
from dataclasses import asdict
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

from src.controllers import PIController
from src.firmware_config import build_firmware_config
from src.foc import CurrentFOCController
from src.speed_control import SpeedController
from src.speed_foc_simulation import run_speed_foc_simulation
from src.transforms import clarke_transform, inverse_clarke_transform, park_transform, inverse_park_transform


ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2", "-ffp-contract=off")
SOURCES = (ROOT/"firmware/src/pmsm_control.c", ROOT/"firmware/src/pmsm_transforms.c")
TOLERANCES = dict(transforms=(8e-6, 2e-6), pi=(2e-4, 2e-5), speed=(2e-4, 2e-5),
                  foc=(5e-3, 2e-5), combined=(5e-3, 2e-5))


def compiler_path():
    explicit = os.environ.get("PMSM_CC")
    if explicit:
        path = shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
        if path is None:
            raise RuntimeError("Configured PMSM_CC compiler not found")
        return path
    return shutil.which("gcc") or shutil.which("clang")


def compile_core(directory, compiler=None):
    compiler = compiler or compiler_path()
    if compiler is None:
        raise RuntimeError("No GCC/Clang found; set PMSM_CC or run Linux CI")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/("pmsm_control.dll" if sys.platform == "win32" else "libpmsm_control.so")
    command = [compiler, *FLAGS, "-shared", *([] if sys.platform == "win32" else ["-fPIC"]),
               "-I", str(ROOT/"firmware/include"), *(str(s) for s in SOURCES), "-lm", "-o", str(path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    version = subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
    return NativeCore(path), dict(compiler=version, flags=list(FLAGS), host=sys.platform,
                                 runtime_precision="IEEE binary32 float; fma contraction disabled")


class Motor(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("Rs", "Ld", "Lq", "psi_f", "J", "B")] + [("pole_pairs", ct.c_uint32)]


class CurrentConfig(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("kp_d", "ki_d", "kp_q", "ki_q", "anti_windup_gain", "dc_bus_voltage", "voltage_limit")] + [("voltage_limit_enabled", ct.c_int)]


class SpeedConfig(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("kp", "ki", "iq_limit", "torque_constant")]


class PiConfig(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("kp", "ki", "output_min", "output_max")] + [(n, ct.c_int) for n in ("lower_limit_enabled", "upper_limit_enabled")]


class PiState(ct.Structure):
    _fields_ = [("integral", ct.c_float)]


class CurrentState(ct.Structure):
    _fields_ = [("d_pi", PiState), ("q_pi", PiState)]


class SpeedState(ct.Structure):
    _fields_ = [("pi", PiState)]


class CurrentInput(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("id_ref", "iq_ref", "id", "iq", "omega_m", "dt")]


class CurrentOutput(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("vd_requested", "vq_requested", "vd", "vq", "requested_magnitude", "magnitude")] + [("saturated", ct.c_int)]


class VoltageOutput(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("vd", "vq", "requested_magnitude", "magnitude")] + [("saturated", ct.c_int)]


class AlphaBeta(ct.Structure):
    _fields_ = [("alpha", ct.c_float), ("beta", ct.c_float)]


class Abc(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in ("a", "b", "c")]


class Dq(ct.Structure):
    _fields_ = [("d", ct.c_float), ("q", ct.c_float)]


class NativeCore:
    def __init__(self, path):
        self.lib = ct.CDLL(str(path))
        ptr = ct.POINTER
        declarations = {
            "clarke": [ct.c_float]*3+[ptr(AlphaBeta)],
            "inverse_clarke": [ct.c_float]*2+[ptr(Abc)],
            "park": [ct.c_float]*3+[ptr(Dq)],
            "inverse_park": [ct.c_float]*3+[ptr(AlphaBeta)],
            "pi_init": [ptr(PiConfig), ptr(PiState)],
            "pi_update": [ptr(PiConfig), ptr(PiState), ct.c_float, ct.c_float, ptr(ct.c_float)],
            "pi_track": [ptr(PiState)]+[ct.c_float]*4,
            "limit_voltage": [ct.c_float, ct.c_float, ct.c_int, ct.c_float, ptr(VoltageOutput)],
            "current_init": [ptr(Motor), ptr(CurrentConfig), ptr(CurrentState)],
            "current_update": [ptr(Motor), ptr(CurrentConfig), ptr(CurrentState), ptr(CurrentInput), ptr(CurrentOutput)],
            "speed_init": [ptr(SpeedConfig), ptr(SpeedState)],
            "speed_update": [ptr(SpeedConfig), ptr(SpeedState)]+[ct.c_float]*3+[ptr(ct.c_float)],
        }
        for name, args in declarations.items():
            function = getattr(self.lib, "pmsm_"+name)
            function.argtypes, function.restype = args, ct.c_int
        for name, cls in (("pi", PiState), ("current", CurrentState), ("speed", SpeedState)):
            function = getattr(self.lib, "pmsm_"+name+"_reset")
            function.argtypes, function.restype = [ptr(cls)], None

    def close(self):
        # Release the host DLL so temporary builds can be removed on Windows.
        import _ctypes
        if self.lib is not None:
            (_ctypes.FreeLibrary if sys.platform == "win32" else _ctypes.dlclose)(self.lib._handle)
            self.lib = None


def c_configs(config):
    return Motor(**asdict(config.motor)), CurrentConfig(**asdict(config.current)), SpeedConfig(**asdict(config.speed))


def f32(value):
    return float(np.float32(value))


def ok(status):
    if status != 0:
        raise AssertionError(f"C kernel returned status {status}")


def fields_dict(value):
    return {name: getattr(value, name) for name, _ in value._fields_}


class ErrorReport:
    def __init__(self):
        self.groups, self.flag_comparisons, self.samples = {}, [], {}

    def compare(self, group, sample, reference, actual):
        atol, rtol = TOLERANCES[group]
        metrics = self.groups.setdefault(group, {})
        self.samples[group] = self.samples.get(group, 0)+1
        differences = {}
        for name, expected in reference.items():
            value = actual[name]
            absolute = abs(float(value)-float(expected))
            relative = absolute/abs(expected) if abs(expected) >= 1e-6 else None
            budget = atol+rtol*abs(expected)
            if not np.isfinite(absolute) or absolute > budget:
                raise AssertionError(f"{group} {sample} {name}: error {absolute} > frozen budget {budget}")
            metric = metrics.setdefault(name, dict(max_absolute_error=-1, max_relative_error=0, worst_sample=None))
            if absolute > metric["max_absolute_error"]:
                metric.update(max_absolute_error=absolute, worst_sample=sample,
                              reference_at_worst=expected, c_at_worst=value)
            if relative is not None:
                if relative > metric["max_relative_error"]:
                    metric.update(max_relative_error=relative, worst_relative_sample=sample,
                                  relative_reference=expected, relative_c=value)
            differences[name] = absolute
        return differences

    def flags(self, stream, sample, reference, actual, magnitude, limit):
        distance = abs(magnitude-limit)
        envelope = 16*2**-24*(abs(magnitude)+abs(limit))
        near = distance <= envelope
        agree = bool(reference) == bool(actual)
        if not near and not agree:
            raise AssertionError(f"Saturation disagreement outside rounding envelope: {stream} {sample}")
        self.flag_comparisons.append(dict(stream=stream, sample=sample, reference_flag=bool(reference),
            c_flag=bool(actual), agree=agree, near_boundary=near, distance_v=distance,
            boundary_rounding_envelope_v=envelope))

    def summary(self):
        worst = max((dict(group=g, signal=s, **m) for g, signals in self.groups.items()
                     for s, m in signals.items()), key=lambda m: m["max_absolute_error"])
        return dict(metrics=self.groups, sample_counts=self.samples, total_compared_samples=sum(self.samples.values()),
            worst_absolute=worst, saturation_flags=dict(total=len(self.flag_comparisons),
            agreements=sum(r["agree"] for r in self.flag_comparisons),
            nonboundary_comparisons=sum(not r["near_boundary"] for r in self.flag_comparisons),
            nonboundary_agreements=sum(r["agree"] and not r["near_boundary"] for r in self.flag_comparisons),
            boundary_probes=[r for r in self.flag_comparisons if r["near_boundary"]]),
            tolerances={g: dict(atol=a, rtol=r) for g, (a, r) in TOLERANCES.items()},
            relative_error_definition="abs(C-reference)/abs(reference) only when abs(reference)>=1e-6; absolute errors always retained")


def transform_parity(core, report):
    rows = []
    xyz = ((0, 0, 0), (1, -.5, -.5), (-3, 2, 1), (20, -7, -13), (.001, -.002, .004), (2, 2, 2))
    pairs = ((0, 0), (1, 0), (0, -2), (-3, 2), (20, -10), (.002, -.003))
    angles = (0, np.pi/6, -np.pi/4, np.pi/2, -np.pi/2, np.pi, -np.pi, 1.7*np.pi)
    for name, reference, cls, inputs in (
        ("clarke", clarke_transform, AlphaBeta, xyz),
        ("inverse_clarke", inverse_clarke_transform, Abc, pairs),
        ("park", park_transform, Dq, [(*v, a) for v in pairs for a in angles]),
        ("inverse_park", inverse_park_transform, AlphaBeta, [(*v, a) for v in pairs for a in angles])):
        for k, inp in enumerate(inputs):
            inp = tuple(map(f32, inp))
            expected = dict(zip((n for n, _ in cls._fields_), reference(*inp)))
            actual = cls()
            ok(getattr(core.lib, "pmsm_"+name)(*inp, ct.byref(actual)))
            differences = report.compare("transforms", f"{name}:{k}", expected, fields_dict(actual))
            rows.append(dict(stream=name, sample=k, **{f"input_{i}": v for i, v in enumerate(inp)},
                **{f"python_{n}": float(v) for n, v in expected.items()},
                **{f"c_{n}": v for n, v in fields_dict(actual).items()}, **{f"error_{n}": v for n, v in differences.items()}))
    return rows


def pi_parity(core, report):
    rows = []
    errors = [0]*8+[4]*24+[-2.5]*24+[0]*8+[.2, -.2]*16+[6, -6]*16
    for limited in (False, True):
        config = PiConfig(1.75, 23.5, -.75, .75, int(limited), int(limited))
        state = PiState()
        ok(core.lib.pmsm_pi_init(ct.byref(config), ct.byref(state)))
        python = PIController(1.75, 23.5, -.75 if limited else None, .75 if limited else None)
        for k, error in enumerate(errors):
            error, dt = f32(error), f32(.002)
            output = ct.c_float()
            expected = python.update(error, dt)
            ok(core.lib.pmsm_pi_update(ct.byref(config), ct.byref(state), error, dt, ct.byref(output)))
            tracking = k % 8 == 0
            applied, requested, gain = map(f32, (.2*np.sin(k), .9 if k%16 == 0 else -.9, 7))
            if tracking:
                python.track_output(applied, requested, dt, gain)
                ok(core.lib.pmsm_pi_track(ct.byref(state), applied, requested, dt, gain))
            reference, actual = dict(output=expected, integral=python.integral), dict(output=output.value, integral=state.integral)
            differences = report.compare("pi", f"{'limited' if limited else 'free'}:{k}", reference, actual)
            rows.append(dict(stream="pi_limited" if limited else "pi_free", sample=k, error_input=error, dt=dt,
                tracking=tracking, tracking_applied=applied, tracking_requested=requested, tracking_gain=gain,
                **{f"python_{n}": v for n, v in reference.items()}, **{f"c_{n}": v for n, v in actual.items()},
                **{f"error_{n}": v for n, v in differences.items()}))
    return rows


class RecordedPI(PIController):
    def update(self, error, dt):
        self.last_output = super().update(error, dt)
        return self.last_output


def reference_foc(parameters, bus):
    controller = CurrentFOCController(parameters, dc_bus_voltage=bus)
    # Instrument only outputs, preserving original update/track methods and gains.
    controller.pi_d = RecordedPI(controller.pi_d.kp, controller.pi_d.ki)
    controller.pi_q = RecordedPI(controller.pi_q.kp, controller.pi_q.ki)
    return controller


def python_foc_step(controller, inp):
    vd, vq = controller.update(*inp)
    id_ref, iq_ref, id_, iq, omega_m, dt = inp
    p = controller.params
    omega_e = p.pole_pairs*omega_m
    return dict(vd_requested=controller.pi_d.last_output-omega_e*p.Lq*iq,
        vq_requested=controller.pi_q.last_output+omega_e*(p.Ld*id_+p.psi_f), vd=vd, vq=vq,
        requested_magnitude=controller.requested_voltage_magnitude, magnitude=controller.voltage_magnitude,
        d_integral=controller.pi_d.integral, q_integral=controller.pi_q.integral)


def native_foc_step(core, motor, config, state, inp):
    output = CurrentOutput()
    ok(core.lib.pmsm_current_update(ct.byref(motor), ct.byref(config), ct.byref(state), ct.byref(CurrentInput(*inp)), ct.byref(output)))
    actual = fields_dict(output)
    flag = actual.pop("saturated")
    return {**actual, "d_integral": state.d_pi.integral, "q_integral": state.q_pi.integral}, flag


def float32_foc_step(config, state, inp):
    """Secondary diagnostic: explicit binary32 operations, not the acceptance reference."""
    f = np.float32
    m, c = config.motor, config.current
    dr, qr, id_, iq, wm, dt = map(f, inp)
    ed, eq = f(dr-id_), f(qr-iq)
    state[0] = f(state[0]+f(f(f(c.ki_d)*ed)*dt))
    state[1] = f(state[1]+f(f(f(c.ki_q)*eq)*dt))
    w = f(f(m.pole_pairs)*wm)
    vd = f(f(f(c.kp_d)*ed+state[0])-f(f(w*f(m.Lq))*iq))
    vq = f(f(f(c.kp_q)*eq+state[1])+f(w*f(f(f(m.Ld)*id_)+f(m.psi_f))))
    requested = f(np.hypot(vd, vq))
    ad, aq = vd, vq
    if c.voltage_limit_enabled and requested > f(c.voltage_limit):
        scale = f(f(c.voltage_limit)/requested)
        ad, aq = f(vd*scale), f(vq*scale)
        state[0] = f(state[0]+f(f(f(c.anti_windup_gain)*dt)*f(ad-vd)))
        state[1] = f(state[1]+f(f(f(c.anti_windup_gain)*dt)*f(aq-vq)))
    return dict(vd_requested=float(vd), vq_requested=float(vq), vd=float(ad), vq=float(aq),
                d_integral=float(state[0]), q_integral=float(state[1]))


def foc_parity(core, report, full, parameters):
    rows, diagnostic = [], {}
    for bus in (48.0, 6.0, None):
        exported = build_firmware_config(full, dc_bus_voltage_v=bus)
        motor, config, _ = c_configs(exported)
        state = CurrentState()
        ok(core.lib.pmsm_current_init(ct.byref(motor), ct.byref(config), ct.byref(state)))
        python = reference_foc(parameters, bus)
        f32_state = [np.float32(0), np.float32(0)]
        for k in range(256):
            speed = (20, 400, 0, -300)[k//64]
            inp = tuple(map(f32, (.4*np.sin(k*.13), 6*np.sin(k*.09), .7*np.sin(k*.1),
                                2*np.cos(k*.07), speed, 20e-6 if k%2 else 40e-6)))
            reference = python_foc_step(python, inp)
            actual, flag = native_foc_step(core, motor, config, state, inp)
            sample = f"bus={bus}:{k}"
            differences = report.compare("foc", sample, reference, actual)
            if bus is not None:
                report.flags("foc", sample, python.voltage_saturated, flag, reference["requested_magnitude"], python.voltage_limit)
            elif python.voltage_saturated or flag:
                raise AssertionError("Disabled voltage limiting reported saturation")
            rounded = float32_foc_step(exported, f32_state, inp)
            for n, value in rounded.items():
                diagnostic[n] = max(diagnostic.get(n, 0), abs(actual[n]-value))
            rows.append(dict(stream=f"foc_bus_{bus}", sample=k, **dict(zip((n for n, _ in CurrentInput._fields_), inp)),
                python_saturated=python.voltage_saturated, c_saturated=bool(flag),
                **{f"python_{n}": v for n, v in reference.items()}, **{f"c_{n}": v for n, v in actual.items()},
                **{f"error_{n}": v for n, v in differences.items()}))
    return rows, diagnostic


def speed_parity(core, report, full, parameters):
    config = c_configs(build_firmware_config(full))[2]
    state = SpeedState()
    ok(core.lib.pmsm_speed_init(ct.byref(config), ct.byref(state)))
    python = SpeedController(parameters)
    rows = []
    for k in range(256):
        ref, measured = ((100, 0), (-100, 0), (40, 39), (-40, -39))[k//64]
        ref, measured, dt = map(f32, (ref, measured, .001))
        expected = python.update(ref, measured, dt)
        output = ct.c_float()
        ok(core.lib.pmsm_speed_update(ct.byref(config), ct.byref(state), ref, measured, dt, ct.byref(output)))
        reference, actual = dict(iq_ref=expected, integral=python.pi.integral), dict(iq_ref=output.value, integral=state.pi.integral)
        differences = report.compare("speed", k, reference, actual)
        rows.append(dict(stream="speed", sample=k, omega_ref=ref, omega_measured=measured, dt=dt,
            **{f"python_{n}": v for n, v in reference.items()}, **{f"c_{n}": v for n, v in actual.items()},
            **{f"error_{n}": v for n, v in differences.items()}))
    return rows


def combined_parity(core, report, full, parameters, plant):
    config = build_firmware_config(full, dc_bus_voltage_v=24)
    motor, current_cfg, speed_cfg = c_configs(config)
    cs, ss = CurrentState(), SpeedState()
    ok(core.lib.pmsm_current_init(ct.byref(motor), ct.byref(current_cfg), ct.byref(cs)))
    ok(core.lib.pmsm_speed_init(ct.byref(speed_cfg), ct.byref(ss)))
    trace = run_speed_foc_simulation(plant_params=plant, controller_params=parameters, dc_bus_voltage=24)
    python_c, python_s = reference_foc(parameters, 24), SpeedController(parameters)
    rows = []
    omega_ref, dt = f32(1000*2*np.pi/60), f32(20e-6)
    for k in range(len(trace["time"])):
        id_, iq, speed, iq_reference = map(f32, (trace["feedback_id"][k], trace["feedback_iq"][k],
            trace["feedback_speed_rad_s"][k], trace["iq_ref"][k]))
        # SAME recorded FOC reference on both sides; no plant or upstream divergence.
        inp = (0., iq_reference, id_, iq, speed, dt)
        reference = python_foc_step(python_c, inp)
        reference.update(iq_ref=python_s.update(omega_ref, speed, dt), speed_integral=python_s.pi.integral)
        actual, flag = native_foc_step(core, motor, current_cfg, cs, inp)
        output = ct.c_float()
        ok(core.lib.pmsm_speed_update(ct.byref(speed_cfg), ct.byref(ss), omega_ref, speed, dt, ct.byref(output)))
        actual.update(iq_ref=output.value, speed_integral=ss.pi.integral)
        differences = report.compare("combined", k, reference, actual)
        report.flags("combined", k, python_c.voltage_saturated, flag,
                     reference["requested_magnitude"], python_c.voltage_limit)
        rows.append(dict(sample=k, time_s=float(trace["time"][k]), id_ref=0, iq_reference_input=iq_reference,
            id=id_, iq=iq, omega_m=speed, omega_ref=omega_ref, dt=dt,
            python_saturated=python_c.voltage_saturated, c_saturated=bool(flag),
            **{f"python_{n}": v for n, v in reference.items()}, **{f"c_{n}": v for n, v in actual.items()},
            **{f"error_{n}": v for n, v in differences.items()}))
    # Comparison includes EVERY step. CSV keeps uniform samples AND every signal's
    # absolute/relative worst samples, so downsampling retains each reported peak.
    selected = set(range(0, len(rows), 25)) | {len(rows)-1}
    selected.update(m["worst_sample"] for m in report.groups["combined"].values())
    selected.update(m["worst_relative_sample"] for m in report.groups["combined"].values()
                    if "worst_relative_sample" in m)
    selected.update(r["sample"] for r in report.flag_comparisons if r["stream"] == "combined" and not r["agree"])
    return [rows[k] for k in sorted(selected)], len(rows)


def boundary_parity(core, report):
    rows = []
    limit = f32(12/np.sqrt(3))
    for angle in np.linspace(0, 2*np.pi, 32, endpoint=False):
        for offset in (-1, 0, 1):
            radial = np.nextafter(np.float32(limit), np.float32(np.inf if offset>0 else -np.inf)) if offset else np.float32(limit)
            vd, vq = map(f32, (float(radial)*np.cos(angle), float(radial)*np.sin(angle)))
            magnitude = float(np.hypot(vd, vq))
            flag = magnitude > limit  # SAME float32-representable limit, float64 norm
            scale = limit/magnitude if flag else 1.
            expected = dict(vd=vd*scale, vq=vq*scale, requested_magnitude=magnitude,
                            magnitude=float(np.hypot(vd*scale, vq*scale)))
            output = VoltageOutput()
            ok(core.lib.pmsm_limit_voltage(vd, vq, 1, limit, ct.byref(output)))
            actual = fields_dict(output)
            c_flag = actual.pop("saturated")
            sample = len(rows)
            difference = report.compare("foc", f"boundary:{sample}", expected, actual)
            report.flags("boundary", sample, flag, c_flag, magnitude, limit)
            rows.append(dict(stream="boundary", sample=sample, input_vd=vd, input_vq=vq, voltage_limit=limit,
                python_saturated=flag, c_saturated=bool(c_flag),
                **{f"python_{n}": v for n, v in expected.items()}, **{f"c_{n}": v for n, v in actual.items()},
                **{f"error_{n}": v for n, v in difference.items()}))
    return rows


def run_parity(core, full, parameters, plant):
    report = ErrorReport()
    vectors = transform_parity(core, report)+pi_parity(core, report)
    current_rows, f32_diagnostic = foc_parity(core, report, full, parameters)
    vectors += current_rows+speed_parity(core, report, full, parameters)+boundary_parity(core, report)
    trace, count = combined_parity(core, report, full, parameters, plant)
    summary = report.summary()
    summary["secondary_binary32_foc_max_absolute_errors"] = f32_diagnostic
    summary["trace_artifact"] = dict(compared_all_steps=count, retained_rows=len(trace), uniform_stride=25,
        also_retained="Worst absolute/relative samples of every signal and every flag disagreement")
    return summary, vectors, trace
