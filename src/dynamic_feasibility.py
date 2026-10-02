"""Forward id=0 transition analysis from accepted commissioning point estimates.

The quasi-steady torque envelope gives an optimistic transition-time estimate,
not a certified lower bound on arbitrary full-dq transients. A second prediction
uses the repository's actual cascaded controller on the commissioned model.
Neither prediction receives plant truth or changes identification quality.
"""

from dataclasses import dataclass
from math import isclose, isfinite, pi, sqrt
from numbers import Real

import numpy as np

from src.motor import PMSMParameters
from src.operating_feasibility import OperatingFeasibility, OperatingPointRequest, assess_operating_point
from src.speed_foc_simulation import run_speed_foc_simulation


ASSUMPTIONS = (
    "Forward acceleration, nonnegative speed/load, constant external resisting load.",
    "Accepted identified point estimates; no uncertainty reserve or hardware guarantee.",
    "Physics envelope assumes id=0 and instantaneous quasi-steady available iq.",
    "Ideal linear SVPWM Vdc/sqrt(3); no field weakening or MTPA.",
    "Controller prediction uses existing 300 Hz current / 10 Hz speed PI tuning.",
    "Initial dq currents and PI integrators are zero; constant load starts at t=0.",
    "A qualified sampled hold within the deadline is not permanent settling.",
)


@dataclass(frozen=True)
class DynamicOperatingRequest:
    initial_speed_rpm: float
    target_speed_rpm: float
    load_torque_nm: float
    dc_bus_voltage_v: float
    current_limit_a: float
    deadline_s: float
    speed_tolerance_fraction: float = 0.01
    minimum_speed_tolerance_rpm: float = 1.0
    hold_time_s: float = 0.1

    def __post_init__(self):
        for name, value in vars(self).items():
            if (not isinstance(value, Real) or isinstance(value, bool) or not isfinite(value)
                    or value < 0 or (name not in ("initial_speed_rpm", "load_torque_nm",
                                                 "speed_tolerance_fraction") and value == 0)):
                raise ValueError(f"dynamic.invalid_request: {name}")
        if self.target_speed_rpm <= self.initial_speed_rpm or self.speed_tolerance_fraction >= 1:
            raise ValueError("dynamic.unsupported_request: forward acceleration / fractional tolerance <1 required")

    @property
    def speed_tolerance_rpm(self):
        return max(self.minimum_speed_tolerance_rpm,
                   self.speed_tolerance_fraction * self.target_speed_rpm)

    @property
    def lower_band_rpm(self):
        return max(0.0, self.target_speed_rpm - self.speed_tolerance_rpm)


@dataclass(frozen=True)
class DynamicAnalysisConfig:
    simulation_dt_s: float = 40e-6
    initial_path_points: int = 257
    maximum_path_points: int = 4097
    relative_time_tolerance: float = 1e-3
    trace_interval_s: float = 1e-3

    def __post_init__(self):
        if (any(not isinstance(v, int) or isinstance(v, bool) or v < 3 for v in
                (self.initial_path_points, self.maximum_path_points))
                or self.maximum_path_points < self.initial_path_points
                or any(not isinstance(v, Real) or isinstance(v, bool) or not isfinite(v) or v <= 0 for v in
                       (self.simulation_dt_s, self.relative_time_tolerance, self.trace_interval_s))):
            raise ValueError("dynamic.invalid_analysis_config")


@dataclass(frozen=True)
class CapabilityPoint:
    speed_rpm: float
    voltage_limited_iq_a: float
    available_iq_a: float
    available_torque_nm: float
    maximum_acceleration_rad_s2: float
    limiting_factor: str
    nonnegative_voltage_domain: bool


@dataclass(frozen=True)
class PhysicalCapability:
    tolerance_band_reachable: bool
    optimistic_min_transition_time_s: float | None
    optimistic_min_completion_time_s: float | None
    physical_deadline_not_ruled_out: bool | None
    limiting_speed_rpm: float | None
    bottleneck_speed_rpm: float
    minimum_acceleration_margin_rad_s2: float
    integration_converged: bool
    integration_change_s: float | None
    current_limited_on_path: bool
    voltage_limited_on_path: bool
    coincident_limits_on_path: bool
    trajectory: tuple[CapabilityPoint, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PredictionSample:
    time_s: float
    speed_rpm: float
    iq_reference_a: float
    voltage_utilization: float


@dataclass(frozen=True)
class ControllerPrediction:
    predicted_closed_loop_success: bool
    first_band_entry_time_s: float | None
    qualified_band_entry_time_s: float | None
    hold_completion_time_s: float | None
    in_band_at_deadline: bool
    finite_signals: bool
    current_reference_within_limit: bool
    maximum_measured_current_a: float
    minimum_speed_rpm: float
    maximum_voltage_utilization: float
    saturation_fraction: float
    trace: tuple[PredictionSample, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DynamicFeasibilityResult:
    request: DynamicOperatingRequest
    exact_target_steady_state: OperatingFeasibility
    tolerance_band_steady_state: OperatingFeasibility
    physical: PhysicalCapability
    controller: ControllerPrediction
    reasons: tuple[str, ...]
    assumptions: tuple[str, ...] = ASSUMPTIONS


def _commissioned_model(commissioning):
    if not commissioning.quality.accepted:
        raise ValueError("dynamic.commissioning_not_accepted")
    try:
        e = commissioning.electrical.electrical
        f = commissioning.electrical.flux
        m = commissioning.mechanical.estimate
        p = commissioning.electrical.pole_pairs
        values = {"Rs": e.Rs, "Ld": e.Ld, "Lq": e.Lq, "psi_f": f.psi_f, "J": m.J, "B": m.B}
    except AttributeError as exc:
        raise ValueError("dynamic.missing_full_estimates") from exc
    if (not isinstance(p, int) or isinstance(p, bool) or p < 1
            or any(not isinstance(v, Real) or not isfinite(v) or v <= 0
                   for k, v in values.items() if k != "B")
            or not isinstance(values["B"], Real) or not isfinite(values["B"]) or values["B"] < 0):
        raise ValueError("dynamic.invalid_identified_parameters")
    return PMSMParameters(**values, pole_pairs=p)


def _capability_point(model, request, speed_rpm):
    omega = speed_rpm * 2*pi/60
    omega_e = model.pole_pairs * omega
    emf = omega_e * model.psi_f
    limit = request.dc_bus_voltage_v/sqrt(3)
    a = (omega_e*model.Lq)**2 + model.Rs**2
    b = 2*model.Rs*emf
    reserve = (limit-emf)*(limit+emf)  # -c, without subtracting nearly equal squares
    if not all(isfinite(v) for v in (a, b, reserve)) or a <= 0:
        raise ValueError("dynamic.nonfinite_voltage_quadratic")
    domain = reserve >= 0
    if domain:
        discriminant = b*b + 4*a*reserve
        if not isfinite(discriminant) or discriminant < 0:
            raise ValueError("dynamic.invalid_voltage_discriminant")
        # Positive root of a iq²+b iq-reserve=0, rationalized to avoid cancellation.
        denominator = b + sqrt(discriminant)
        iq_voltage = 0.0 if reserve == 0 else 2*reserve/denominator
    else:
        iq_voltage = 0.0  # even iq=0 is outside the id=0 steady voltage domain
    iq = min(request.current_limit_a, iq_voltage)
    torque = 1.5*model.pole_pairs*model.psi_f*iq
    acceleration = (torque-request.load_torque_nm-model.B*omega)/model.J
    if not all(isfinite(v) for v in (iq_voltage, torque, acceleration)):
        raise ValueError("dynamic.nonfinite_capability")
    # Numerical coincidence only; this is not a physical uncertainty margin.
    if isclose(iq_voltage, request.current_limit_a, rel_tol=1e-9, abs_tol=1e-12):
        factor = "coincident"
    else:
        factor = "current" if iq_voltage > request.current_limit_a else "voltage"
    return CapabilityPoint(float(speed_rpm), iq_voltage, iq, torque, acceleration, factor, domain)


def assess_physical_capability(commissioning, request, config=DynamicAnalysisConfig()):
    """Integrate dω/alpha_max to the lower band edge using identified J/B.

    For positive parameters in this forward id=0 model, available current and
    alpha_max are nonincreasing with speed. Endpoint/bisection checks therefore
    cannot miss an interior nonpositive-acceleration region.
    """
    model = _commissioned_model(commissioning)
    start, end = request.initial_speed_rpm, max(request.initial_speed_rpm, request.lower_band_rpm)
    first, last = (_capability_point(model, request, s) for s in (start, end))
    reachable = last.nonnegative_voltage_domain and (last.maximum_acceleration_rad_s2 > 0
                 or (start == end and last.maximum_acceleration_rad_s2 >= 0))
    limiting_speed = None
    reasons = []
    if not reachable:
        reasons.append("dynamic.nonpositive_acceleration")
        lo, hi = start, end
        if first.maximum_acceleration_rad_s2 > 0:
            for _ in range(60):
                mid = .5*(lo+hi)
                if _capability_point(model, request, mid).maximum_acceleration_rad_s2 > 0:
                    lo = mid
                else:
                    hi = mid
        else:
            hi = start
        limiting_speed = hi
    points = config.initial_path_points
    previous = change = minimum_time = None
    converged = start == end or not reachable
    while True:
        path = tuple(_capability_point(model, request, s) for s in np.linspace(start, end, points))
        if not reachable:
            break
        if start == end:
            minimum_time = 0.0
            break
        omega = np.array([p.speed_rpm for p in path]) * 2*pi/60
        inverse_acceleration = 1/np.array([p.maximum_acceleration_rad_s2 for p in path])
        minimum_time = float(np.sum(.5*(inverse_acceleration[:-1]+inverse_acceleration[1:])*np.diff(omega)))
        if previous is not None:
            change = abs(minimum_time-previous)
            converged = change <= config.relative_time_tolerance * max(minimum_time, 1e-12)
        if converged or points >= config.maximum_path_points:
            break
        previous = minimum_time
        points = min(2*points-1, config.maximum_path_points)
    completion = None if minimum_time is None else minimum_time+request.hold_time_s
    not_ruled_out = (False if not reachable else None if not converged else completion <= request.deadline_s)
    if reachable and not converged:
        reasons.append("dynamic.integration_resolution")
    if not_ruled_out is False and reachable:
        reasons.append("dynamic.deadline_too_short")
    factors = {p.limiting_factor for p in path}
    return PhysicalCapability(reachable, minimum_time, completion, not_ruled_out, limiting_speed,
        last.speed_rpm, last.maximum_acceleration_rad_s2, converged, change,
        "current" in factors, "voltage" in factors, "coincident" in factors, path, tuple(reasons))


def evaluate_controller_trace(simulation, request, dt, trace_interval_s=1e-3):
    """Independent sampled band/hold criterion, shared with evaluation experiments.

    Historical simulator logs each post-step state at k*dt. Interpret that state
    at (k+1)*dt here without changing historical logging/default trajectories.
    A qualified hold may finish anywhere before the deadline; this definition
    keeps success monotonic when an otherwise identical deadline is extended.
    """
    mask = simulation["time"] + dt <= request.deadline_s + 8*np.finfo(float).eps*request.deadline_s
    time = np.r_[0.0, (simulation["time"]+dt)[mask]]
    speed = np.r_[request.initial_speed_rpm, simulation["rpm"][mask]]
    ref = np.r_[0.0, simulation["iq_ref"][mask]]
    voltage = np.r_[0.0, simulation["voltage_magnitude"][mask]]
    finite = all(np.all(np.isfinite(simulation[key][mask])) for key in (
        "rpm", "id", "iq", "iq_ref", "voltage_d", "voltage_q", "voltage_magnitude"))
    reference_ok = bool(np.all(np.abs(ref) <= request.current_limit_a*(1+16*np.finfo(float).eps)))
    inside = np.abs(speed-request.target_speed_rpm) <= request.speed_tolerance_rpm
    first_entry = float(time[np.flatnonzero(inside)[0]]) if np.any(inside) else None
    entry = completed = None
    run_start = None
    for k, good in enumerate(inside):
        if not good:
            run_start = None
        elif run_start is None:
            run_start = k
        if run_start is not None and time[k]-time[run_start] >= request.hold_time_s-8*np.finfo(float).eps:
            entry, completed = float(time[run_start]), float(time[k])
            break
    success = finite and reference_ok and completed is not None
    reasons = (() if finite else ("dynamic.controller_nonfinite",)) + (
        () if reference_ok else ("dynamic.current_reference_limit",)) + (
        () if completed is not None else ("dynamic.controller_hold_deadline",)) + (
        () if np.min(speed) >= 0 else ("dynamic.reverse_speed_excursion",))
    stride = max(1, round(trace_interval_s/dt))
    selected = np.unique(np.r_[np.arange(0, len(time), stride), len(time)-1])
    samples = tuple(PredictionSample(float(time[k]), float(speed[k]), float(ref[k]),
                    float(voltage[k]/simulation["voltage_limit"])) for k in selected)
    current = np.hypot(simulation["id"][mask], simulation["iq"][mask])
    return ControllerPrediction(bool(success), first_entry, entry, completed, bool(inside[-1]),
        bool(finite), reference_ok, float(np.max(current, initial=0)), float(np.min(speed)),
        float(np.max(voltage)/simulation["voltage_limit"]),
        float(np.mean(simulation["voltage_saturated"][mask])) if np.any(mask) else 0.0,
        samples, reasons)


def assess_dynamic_operating_point(commissioning, request: DynamicOperatingRequest,
                                   config=DynamicAnalysisConfig()):
    """Assess physics and existing-controller prediction; accepted estimates only."""
    model = _commissioned_model(commissioning)
    physical = assess_physical_capability(commissioning, request, config)
    exact, band = (assess_operating_point(commissioning, OperatingPointRequest(
        speed, request.load_torque_nm, request.dc_bus_voltage_v, request.current_limit_a))
        for speed in (request.target_speed_rpm, request.lower_band_rpm))
    simulation = run_speed_foc_simulation(plant_params=model, controller_params=model,
        dt=config.simulation_dt_s, simulation_time=request.deadline_s,
        initial_speed_rpm=request.initial_speed_rpm, speed_ref_rpm=request.target_speed_rpm,
        load_step_time=0, load_step_torque=request.load_torque_nm,
        dc_bus_voltage=request.dc_bus_voltage_v, current_limit_a=request.current_limit_a)
    controller = evaluate_controller_trace(simulation, request, config.simulation_dt_s, config.trace_interval_s)
    reasons = (() if exact.feasible else ("dynamic.exact_target_steady_infeasible",)) + (
        () if band.feasible else ("dynamic.tolerance_band_steady_infeasible",)) + physical.reasons + controller.reasons
    return DynamicFeasibilityResult(request, exact, band, physical, controller, reasons)
