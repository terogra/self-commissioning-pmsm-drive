"""Steady-state id=0 operating envelope, separate from identification quality.

Normal entry points require accepted full commissioning. No true plant object,
inertia, controller outcome, or quality-threshold adjustment enters the model.
"""

from dataclasses import dataclass
from math import hypot, isfinite, pi, sqrt
from numbers import Real


ASSUMPTIONS = (
    "Forward motoring: nonnegative requested speed and external resisting load.",
    "Steady state with id=0; no field weakening or MTPA.",
    "Known requested external load, constant viscous friction, and accepted point estimates.",
    "Ideal linear SVPWM phase-neutral peak dq voltage limit Vdc/sqrt(3).",
    "Current limit is a configured simulation/design constraint, not a hardware rating.",
    "No guarantee of transient tracking, parameter uncertainty coverage, or hardware safety.",
)


@dataclass(frozen=True)
class OperatingPointRequest:
    speed_rpm: float
    load_torque_nm: float
    dc_bus_voltage_v: float
    current_limit_a: float = 5.0

    def __post_init__(self):
        for name, value in vars(self).items():
            if (not isinstance(value, Real) or isinstance(value, bool) or not isfinite(value)
                    or value < 0 or (name in ("dc_bus_voltage_v", "current_limit_a") and value == 0)):
                raise ValueError(f"operating.invalid_request: {name}")


@dataclass(frozen=True)
class OperatingFeasibility:
    steady_state_feasible: bool
    current_feasible: bool
    voltage_feasible: bool
    requested_speed_rpm: float
    requested_load_torque_nm: float
    required_torque_nm: float
    required_id_a: float
    required_iq_a: float
    required_current_magnitude_a: float
    current_limit_a: float
    current_margin_a: float
    current_utilization: float
    required_vd_v: float
    required_vq_v: float
    required_voltage_magnitude_v: float
    voltage_limit_v: float
    voltage_margin_v: float
    voltage_utilization: float
    electrical_speed_rad_s: float
    reasons: tuple[str, ...]
    assumptions: tuple[str, ...] = ASSUMPTIONS

    @property
    def feasible(self):
        return self.steady_state_feasible

    @property
    def classification(self):
        if self.feasible:
            return "feasible"
        if not self.current_feasible and not self.voltage_feasible:
            return "both_limited"
        return "current_limited" if not self.current_feasible else "voltage_limited"


def _evaluate_id_zero(*, Rs, Lq, psi_f, B, pole_pairs, request):
    """Equation kernel; oracle evaluation may call this explicitly outside the API.

    Steady mechanical balance is Te = Tload + B*omega; J has no role.
    At id=0, iq=Te/(1.5*p*psi), vd=-omega_e*Lq*iq,
    vq=Rs*iq+omega_e*psi. Equality to either limit is included, with zero reserve.
    """
    values = (Rs, Lq, psi_f, B)
    if (any(not isinstance(v, Real) or not isfinite(v) for v in values)
            or min(Rs, Lq, psi_f) <= 0 or B < 0
            or not isinstance(pole_pairs, int) or isinstance(pole_pairs, bool) or pole_pairs < 1):
        raise ValueError("operating.invalid_parameters")
    omega = request.speed_rpm * 2*pi/60
    omega_e = pole_pairs * omega
    torque = request.load_torque_nm + B*omega
    iq = torque/(1.5*pole_pairs*psi_f)
    vd = -omega_e*Lq*iq
    vq = Rs*iq + omega_e*psi_f
    current, voltage = abs(iq), hypot(vd, vq)
    limit = request.dc_bus_voltage_v/sqrt(3)
    current_margin, voltage_margin = request.current_limit_a-current, limit-voltage
    current_use, voltage_use = current/request.current_limit_a, voltage/limit
    if not all(isfinite(v) for v in (omega_e, torque, iq, vd, vq, current, voltage,
                                     current_margin, voltage_margin, current_use, voltage_use)):
        raise ValueError("operating.invalid_request: nonfinite derived values")
    current_ok, voltage_ok = bool(current_margin >= 0), bool(voltage_margin >= 0)
    reasons = (() if current_ok else ("operating.current_limit",)) + (() if voltage_ok else ("operating.voltage_limit",))
    return OperatingFeasibility(current_ok and voltage_ok, current_ok, voltage_ok,
        request.speed_rpm, request.load_torque_nm, torque, 0.0, iq, current,
        request.current_limit_a, current_margin, current_use, vd, vq, voltage, limit,
        voltage_margin, voltage_use, omega_e, reasons)


def assess_operating_point(commissioning, request: OperatingPointRequest):
    """Read accepted estimates only; never fall back to assumed/true parameters.

    Unaccepted/missing commissioning is unavailable analysis, not operating
    infeasibility and not a change to either identification-quality decision.
    """
    if not commissioning.quality.accepted:
        raise ValueError("operating.commissioning_not_accepted")
    electrical = commissioning.electrical.electrical
    flux = commissioning.electrical.flux
    mechanical = commissioning.mechanical.estimate
    if electrical is None or flux is None or mechanical is None:
        raise ValueError("operating.missing_estimates")
    return _evaluate_id_zero(Rs=electrical.Rs, Lq=electrical.Lq, psi_f=flux.psi_f,
                             B=mechanical.B, pole_pairs=commissioning.electrical.pole_pairs, request=request)


def operating_envelope(commissioning, speeds_rpm, loads_nm, dc_bus_voltage_v, current_limit_a):
    """Deterministic load-major, then speed-major grid; retain every point."""
    return [assess_operating_point(commissioning, OperatingPointRequest(speed, load, dc_bus_voltage_v, current_limit_a))
            for load in loads_nm for speed in speeds_rpm]
