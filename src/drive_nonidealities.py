"""Averaged signal-chain imperfections outside commissioning decisions.

All quantities use amplitude-invariant phase-neutral peak conventions. Structured
gain/bias/quantization errors are deterministic, not MeasurementNoise metadata.
This is neither a switching inverter nor a hardware protection model.
"""

from collections import deque
from dataclasses import dataclass, replace
from math import cos, hypot, isfinite, sin, sqrt
from numbers import Real

import numpy as np

from src.transforms import (clarke_transform, inverse_clarke_transform,
                            inverse_park_transform, park_transform)


def _finite(value, name, minimum=None):
    if (not isinstance(value, Real) or isinstance(value, bool) or not isfinite(value)
            or minimum is not None and value < minimum):
        raise ValueError(f"nonideality.invalid_{name}")


def _channels(values, size, name, positive=False):
    if not isinstance(values, tuple) or len(values) != size:
        raise ValueError(f"nonideality.invalid_{name}")
    for v in values:
        _finite(v, name)
        if positive and v <= 0:
            raise ValueError(f"nonideality.invalid_{name}")


@dataclass(frozen=True)
class CurrentMeasurementErrors:
    phase_gains: tuple[float, float, float] = (1., 1., 1.)
    phase_offsets_a: tuple[float, float, float] = (0., 0., 0.)
    quantum_a: float = 0.

    def __post_init__(self):
        _channels(self.phase_gains, 3, "current_gains", True)
        _channels(self.phase_offsets_a, 3, "current_offsets")
        _finite(self.quantum_a, "current_quantum", 0)


@dataclass(frozen=True)
class VoltageMeasurementErrors:
    dq_gains: tuple[float, float] = (1., 1.)
    dq_offsets_v: tuple[float, float] = (0., 0.)
    quantum_v: float = 0.
    # 'command' reconstructs the FOC/excitation command, not hidden terminals.
    source: str = "command"

    def __post_init__(self):
        _channels(self.dq_gains, 2, "voltage_gains", True)
        _channels(self.dq_offsets_v, 2, "voltage_offsets")
        _finite(self.quantum_v, "voltage_quantum", 0)
        if self.source not in ("command", "terminal"):
            raise ValueError("nonideality.invalid_voltage_source")


@dataclass(frozen=True)
class FrameErrors:
    electrical_angle_bias_rad: float = 0.

    def __post_init__(self):
        _finite(self.electrical_angle_bias_rad, "angle_bias")


@dataclass(frozen=True)
class TimingErrors:
    feedback_delay_steps: int = 0
    record_current_delay_samples: int = 0

    def __post_init__(self):
        if any(type(v) is not int or v not in (0, 1) for v in vars(self).values()):
            raise ValueError("nonideality.only_zero_or_one_sample_delay_supported")


@dataclass(frozen=True)
class ActuationErrors:
    phase_sign_voltage_drop_v: float = 0.
    bus_sag_fraction: float = 0.

    def __post_init__(self):
        _finite(self.phase_sign_voltage_drop_v, "phase_voltage_drop", 0)
        _finite(self.bus_sag_fraction, "bus_sag", 0)
        if self.bus_sag_fraction >= 1:
            raise ValueError("nonideality.invalid_bus_sag")


@dataclass(frozen=True)
class OperatingDrift:
    rs_factor: float = 1.

    def __post_init__(self):
        _finite(self.rs_factor, "rs_factor", 0)
        if self.rs_factor == 0:
            raise ValueError("nonideality.invalid_rs_factor")

    def plant_for_operation(self, plant):
        """Simulation boundary only; never mutates prior/commissioned parameters."""
        return plant if self.rs_factor == 1 else replace(plant, Rs=plant.Rs*self.rs_factor)


@dataclass(frozen=True)
class DriveNonidealities:
    current: CurrentMeasurementErrors = CurrentMeasurementErrors()
    voltage: VoltageMeasurementErrors = VoltageMeasurementErrors()
    frame: FrameErrors = FrameErrors()
    timing: TimingErrors = TimingErrors()
    actuation: ActuationErrors = ActuationErrors()
    drift: OperatingDrift = OperatingDrift()

    def __post_init__(self):
        for name, cls in (("current", CurrentMeasurementErrors), ("voltage", VoltageMeasurementErrors),
                          ("frame", FrameErrors), ("timing", TimingErrors),
                          ("actuation", ActuationErrors), ("drift", OperatingDrift)):
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f"nonideality.invalid_{name}_configuration")

    @property
    def has_signal_errors(self):
        return any(getattr(self, name) != cls() for name, cls in (
            ("current", CurrentMeasurementErrors), ("voltage", VoltageMeasurementErrors),
            ("frame", FrameErrors), ("timing", TimingErrors), ("actuation", ActuationErrors)))

    @property
    def is_ideal(self):
        return not self.has_signal_errors and self.drift == OperatingDrift()


def quantize(values, quantum):
    """Nearest quantum in A or V; ties use numpy round-to-even, no clipping."""
    a = np.asarray(values)
    return a if quantum == 0 else np.rint(a/quantum)*quantum


def rotate_dq(dq, angle):
    """Rotate coordinate vector by angle; controller->true uses +angle bias."""
    d, q = dq
    if angle == 0:
        return d, q
    c, s = cos(angle), sin(angle)
    return c*d-s*q, s*d+c*q


def measure_current(dq, true_angle, config):
    """true dq -> abc -> phase gain/offset/quantum -> measured-angle dq.

    Supports single points and sample arrays. Zero error returns inputs exactly.
    Gaussian output noise is added separately by the existing sampled provider.
    """
    dq = np.asarray(dq)
    bias = config.frame.electrical_angle_bias_rad
    if config.current == CurrentMeasurementErrors():
        if bias == 0:
            return dq
        d, q = dq[..., 0], dq[..., 1]
        return np.stack((np.cos(bias)*d+np.sin(bias)*q,
                         -np.sin(bias)*d+np.cos(bias)*q), axis=-1)
    alpha, beta = inverse_park_transform(dq[..., 0], dq[..., 1], true_angle)
    abc = np.stack(inverse_clarke_transform(alpha, beta), axis=-1)
    abc = quantize(abc*np.asarray(config.current.phase_gains)+config.current.phase_offsets_a,
                   config.current.quantum_a)
    alpha, beta = clarke_transform(*np.moveaxis(abc, -1, 0))
    d, q = park_transform(alpha, beta, np.asarray(true_angle)+bias)
    return np.stack((d, q), axis=-1)


@dataclass(frozen=True)
class AppliedVoltage:
    terminal_d_v: float
    terminal_q_v: float
    actual_bus_voltage_v: float | None
    bus_limited: bool


def apply_voltage(command_dq, true_current_dq, true_angle, command_angle,
                  nominal_bus_voltage_v, config):
    """Command in controller frame -> actual zero-order-held true dq voltage.

    The phase surrogate is -drop*sign(i_phase) with sign(0)=0. Its zero sequence
    is removed by Clarke; this represents only a bounded averaged error. The
    resulting vector is clipped to the ACTUAL sagged bus circle. FOC remains
    unaware of that additional clipping; no anti-windup redesign is hidden here.
    """
    vd, vq = rotate_dq(command_dq, command_angle-true_angle)
    drop = config.actuation.phase_sign_voltage_drop_v
    if drop:
        alpha, beta = inverse_park_transform(*true_current_dq, true_angle)
        phases = inverse_clarke_transform(alpha, beta)
        errors = tuple(-drop*(1. if v > 0 else -1. if v < 0 else 0.) for v in phases)
        ea, eb = clarke_transform(*errors)
        ed, eq = park_transform(ea, eb, true_angle)
        vd, vq = vd+ed, vq+eq
    if nominal_bus_voltage_v is None:
        if config.actuation.bus_sag_fraction:
            raise ValueError("nonideality.bus_sag_requires_nominal_bus")
        actual_bus, limited = None, False
    else:
        actual_bus = nominal_bus_voltage_v*(1-config.actuation.bus_sag_fraction)
        limit = actual_bus/sqrt(3)
        norm = hypot(vd, vq)
        limited = norm > limit
        if limited:
            vd, vq = vd*limit/norm, vq*limit/norm
    return AppliedVoltage(vd, vq, actual_bus, limited)


def estimator_voltage(command_dq, terminal_true_dq, config):
    """Reconstruct in the measured frame; terminal data are optional rig sensing."""
    values = np.asarray(command_dq)
    if config.voltage.source == "terminal":
        t = np.asarray(terminal_true_dq)
        bias = config.frame.electrical_angle_bias_rad
        values = np.stack((np.cos(bias)*t[..., 0]+np.sin(bias)*t[..., 1],
                           -np.sin(bias)*t[..., 0]+np.cos(bias)*t[..., 1]), axis=-1)
    return quantize(values*np.asarray(config.voltage.dq_gains)+config.voltage.dq_offsets_v,
                    config.voltage.quantum_v)


def delayed_samples(values, steps):
    """One record sample late relative to unchanged timestamps/voltage intervals."""
    a = np.asarray(values)
    return a if steps == 0 else np.concatenate((a[:1], a[:-1]), axis=0)


class FeedbackDelay:
    """Delay the (id, iq, speed, measured angle) tuple; hold first value initially."""
    def __init__(self, steps):
        if type(steps) is not int or steps not in (0, 1):
            raise ValueError("nonideality.only_zero_or_one_sample_delay_supported")
        self.steps, self.previous = steps, deque(maxlen=1)

    def sample(self, feedback):
        value = tuple(feedback)
        old = self.previous[0] if self.steps and self.previous else value
        self.previous.append(value)
        return old
