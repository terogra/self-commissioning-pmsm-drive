"""Build binary32 C controller constants from accepted commissioning."""

from dataclasses import dataclass, fields
from pathlib import Path
import re
from numbers import Real

import numpy as np

from src.commissioning import CommissioningRejectedError
from src.foc import CurrentFOCController
from src.full_commissioning import FullCommissioningResult
from src.motor import PMSMParameters
from src.speed_control import SpeedController


@dataclass(frozen=True)
class FirmwareMotorParams:
    Rs: float
    Ld: float
    Lq: float
    psi_f: float
    J: float
    B: float
    pole_pairs: int


@dataclass(frozen=True)
class FirmwareCurrentConfig:
    kp_d: float
    ki_d: float
    kp_q: float
    ki_q: float
    anti_windup_gain: float
    dc_bus_voltage: float
    voltage_limit: float
    voltage_limit_enabled: int


@dataclass(frozen=True)
class FirmwareSpeedConfig:
    kp: float
    ki: float
    iq_limit: float
    torque_constant: float


@dataclass(frozen=True)
class FirmwareConfig:
    motor: FirmwareMotorParams
    current: FirmwareCurrentConfig
    speed: FirmwareSpeedConfig


def _binary32(value):
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError("firmware.invalid_numeric_constant")
    try:
        with np.errstate(over="raise", invalid="raise"):
            rounded = float(np.float32(value))
    except (TypeError, ValueError, FloatingPointError, OverflowError) as exc:
        raise ValueError("firmware.nonfinite_or_unrepresentable_constant") from exc
    if not np.isfinite(rounded):
        raise ValueError("firmware.nonfinite_or_unrepresentable_constant")
    return rounded


def _validate_config(config):
    if not isinstance(config, FirmwareConfig) or not all(isinstance(value, cls) for value, cls in (
            (config.motor, FirmwareMotorParams), (config.current, FirmwareCurrentConfig), (config.speed, FirmwareSpeedConfig))):
        raise TypeError("firmware.requires_built_configuration")
    m, c, s = config.motor, config.current, config.speed
    if type(m.pole_pairs) is not int or not 1 <= m.pole_pairs <= 2**24:
        raise ValueError("firmware.invalid_pole_pairs")
    if type(c.voltage_limit_enabled) is not int or c.voltage_limit_enabled not in (0, 1):
        raise ValueError("firmware.invalid_limit_flag")
    for record in (m, c, s):
        for field in fields(record):
            if field.name not in ("pole_pairs", "voltage_limit_enabled"):
                _binary32(getattr(record, field.name))
    if any(_binary32(getattr(m, n)) <= 0 for n in ("Rs", "Ld", "Lq", "psi_f", "J")) or m.B < 0:
        raise ValueError("firmware.invalid_motor_constants")
    if _binary32(s.iq_limit) <= 0 or _binary32(s.torque_constant) <= 0 or c.anti_windup_gain < 0:
        raise ValueError("firmware.invalid_limits")
    if c.voltage_limit_enabled:
        if _binary32(c.dc_bus_voltage) <= 0 or _binary32(c.voltage_limit) <= 0:
            raise ValueError("firmware.invalid_bus")
        expected = c.dc_bus_voltage/np.sqrt(3)
        if abs(c.voltage_limit-expected) > 4*np.finfo(np.float32).eps*expected:
            raise ValueError("firmware.inconsistent_voltage_limit")
    elif c.dc_bus_voltage != 0 or c.voltage_limit != 0:
        raise ValueError("firmware.disabled_voltage_limit_must_be_zero")


def build_firmware_config(commissioning: FullCommissioningResult, *,
                          current_bandwidth_hz=300.0, natural_frequency_hz=10.0,
                          damping_ratio=1.0, iq_limit_a=5.0, dc_bus_voltage_v=48.0,
                          anti_windup_gain=None) -> FirmwareConfig:
    """Require full acceptance; derive gains by invoking unmodified constructors.

    The prior contains only known pole pairs; all six numerical motor values are
    replaced by full commissioning. No hidden plant or oracle object is accepted.
    Motor values and derived gains are rounded once to binary32 for export.
    """
    if not isinstance(commissioning, FullCommissioningResult):
        raise TypeError("firmware.requires_full_commissioning")
    if not commissioning.quality.accepted:
        raise CommissioningRejectedError(commissioning.quality)
    for value in (current_bandwidth_hz, natural_frequency_hz, iq_limit_a):
        if not np.isfinite(value) or value <= 0:
            raise ValueError("firmware.invalid_tuning")
    if not np.isfinite(damping_ratio) or damping_ratio < 0:
        raise ValueError("firmware.invalid_damping")
    pole_pairs = commissioning.electrical.pole_pairs
    if type(pole_pairs) is not int or not 1 <= pole_pairs <= 2**24:
        raise ValueError("firmware.pole_pairs_must_be_exact_binary32_integer")
    parameters = commissioning.retuned_controller_parameters(PMSMParameters(pole_pairs=pole_pairs))
    motor = FirmwareMotorParams(**{f.name: (pole_pairs if f.name == "pole_pairs" else
        _binary32(getattr(parameters, f.name))) for f in fields(FirmwareMotorParams)})
    if any(getattr(motor, n) <= 0 for n in ("Rs", "Ld", "Lq", "psi_f", "J")) or motor.B < 0:
        raise ValueError("firmware.invalid_motor_constants_after_rounding")
    current = CurrentFOCController(parameters, current_bandwidth_hz, dc_bus_voltage_v, anti_windup_gain)
    speed = SpeedController(parameters, natural_frequency_hz, damping_ratio, iq_limit_a)
    result = FirmwareConfig(motor,
        FirmwareCurrentConfig(*(_binary32(v) for v in (current.pi_d.kp, current.pi_d.ki,
            current.pi_q.kp, current.pi_q.ki, current.anti_windup_gain,
            0 if dc_bus_voltage_v is None else dc_bus_voltage_v,
            0 if current.voltage_limit is None else current.voltage_limit)), int(current.voltage_limit is not None)),
        FirmwareSpeedConfig(*(_binary32(v) for v in (speed.kp, speed.ki, iq_limit_a, speed.kt))))
    if (result.speed.iq_limit <= 0 or result.speed.torque_constant <= 0
            or result.current.voltage_limit_enabled and (result.current.dc_bus_voltage <= 0 or result.current.voltage_limit <= 0)):
        raise ValueError("firmware.invalid_limits_after_rounding")
    _validate_config(result)
    return result


def export_c_header(config: FirmwareConfig, path, *, prefix="commissioned",
                    provenance="Accepted full commissioning; origin must be recorded by the caller.") -> Path:
    """Write a standalone C99 config header with exact binary32 hex literals.

    This serializes configuration; it does not approve a motor or deploy firmware.
    Normal callers obtain config only through build_firmware_config's full gate.
    """
    _validate_config(config)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", prefix):
        raise ValueError("firmware.invalid_c_identifier")
    comment = provenance.replace("*/", "* /").replace("\r", " ").replace("\n", " ")
    guard = prefix.upper()+"_PMSM_CONFIG_H"
    declarations = []
    for label, ctype, record in (("motor", "PmsmMotorParams", config.motor),
                               ("current", "PmsmCurrentConfig", config.current),
                               ("speed", "PmsmSpeedConfig", config.speed)):
        constants = []
        for field in fields(record):
            value = getattr(record, field.name)
            if field.name == "pole_pairs":
                constants.append(f"{value}u")
            elif field.name == "voltage_limit_enabled":
                constants.append(str(value))
            else:
                constants.append(_binary32(value).hex()+"f")
        declarations.append(f"static const {ctype} {prefix}_{label} = {{\n    "+",\n    ".join(constants)+"\n};")
    text = (f"/* Generated binary32 constants. {comment}\n"
            " * Demonstration/configuration only; no hardware validation or safety guarantee. */\n"
            f"#ifndef {guard}\n#define {guard}\n\n#include \"pmsm_config.h\"\n\n"+
            "\n\n".join(declarations)+f"\n\n#endif /* {guard} */\n")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
