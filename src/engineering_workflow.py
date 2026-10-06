"""Run sampled commissioning, controller retuning and operating analysis."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import subprocess
from types import MappingProxyType
from typing import Mapping

import numpy as np

from experiments.nonideality_robustness import scenarios, operation_metrics
from src.adaptive_commissioning import (
    AttemptRecord, Stage, SupervisorResult, _snapshot, _estimator_failure,
    _standstill_quality, run_adaptive_commissioning,
)
from src.commissioning import CommissioningRejectedError, commission_from_measurements
from src.commissioning_quality import CommissioningQuality, QualityPolicy
from src.drive_nonidealities import DriveNonidealities
from src.dynamic_feasibility import DynamicAnalysisConfig, DynamicOperatingRequest, assess_dynamic_operating_point
from src.firmware_config import FirmwareConfig, build_firmware_config, export_c_header
from src.foc import CurrentFOCController
from src.full_commissioning import FullCommissioningResult, MechanicalCommissioningResult, complete_commissioning
from src.identification import ExcitationConfig, simulate_locked_rotor_measurements
from src.mechanical_excitation import MechanicalExcitationConfig, simulate_mechanical_measurements
from src.motor import PMSMParameters
from src.operating_feasibility import OperatingPointRequest, assess_operating_point
from src.rotating_identification import RotatingExcitationConfig, simulate_driven_rotor_measurements
from src.speed_control import SpeedController
from src.speed_foc_simulation import run_speed_foc_simulation
from src.version import __version__, RELEASE_STATUS


ROOT = Path(__file__).resolve().parents[1]
PARAMETER_NAMES = ("Rs", "Ld", "Lq", "psi_f", "J", "B", "pole_pairs")
PARAMETER_UNITS = ("ohm", "H", "H", "Wb", "kg m²", "N m s/rad", "pairs")


@dataclass(frozen=True)
class MotorConfiguration:
    Rs: float = .4
    Ld: float = .001
    Lq: float = .001
    psi_f: float = .025
    J: float = .0002
    B: float = .0001
    pole_pairs: int = 4

    def __post_init__(self):
        if (any(not isfinite(v) or v <= 0 for v in (self.Rs, self.Ld, self.Lq, self.psi_f, self.J))
                or not isfinite(self.B) or self.B < 0 or type(self.pole_pairs) is not int
                or not 1 <= self.pole_pairs <= 2**24):
            raise ValueError("workflow.invalid_motor_configuration")

    def parameters(self):
        return PMSMParameters(**asdict(self))

    @classmethod
    def from_parameters(cls, parameters):
        return cls(**asdict(parameters))


@dataclass(frozen=True)
class EngineeringWorkflowConfig:
    # Explicit SIMULATION TRUTH: never passed to a decision/estimator API.
    simulation_truth: MotorConfiguration = MotorConfiguration(.5, .0012, .0009, .022, .00055, .0002)
    prior_assumptions: MotorConfiguration = MotorConfiguration()
    scenario: str = "ideal"
    mode: str = "one_shot"
    exposure: str = "combined"
    seed: int = 1901
    dc_bus_voltage_v: float = 24.0
    speed_target_rpm: float = 1000.0
    load_torque_nm: float = .05
    current_limit_a: float = 5.0
    deadline_s: float = .6
    hold_time_s: float = .1
    simulation_duration_s: float = .6
    load_step_time_s: float = .3
    simulation_dt_s: float = 40e-6
    standstill: ExcitationConfig = ExcitationConfig(current_noise_std_a=.01, voltage_noise_std_v=.01, speed_noise_std_rad_s=.02)
    rotating: RotatingExcitationConfig = RotatingExcitationConfig(q_voltage_base_v=5, current_noise_std_a=.01, voltage_noise_std_v=.01, speed_noise_std_rad_s=.02)
    mechanical: MechanicalExcitationConfig = MechanicalExcitationConfig()

    def __post_init__(self):
        if self.scenario not in {s.name for s in scenarios()}:
            raise ValueError("workflow.unknown_M17_scenario")
        if self.mode not in ("one_shot", "adaptive") or self.exposure not in ("combined", "commissioning_only", "operation_only"):
            raise ValueError("workflow.invalid_mode_or_exposure")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**31-3:
            raise ValueError("workflow.invalid_seed")
        if self.simulation_truth.pole_pairs != self.prior_assumptions.pole_pairs:
            raise ValueError("workflow.pole_pairs_must_be_explicitly_known_and_consistent")
        OperatingPointRequest(self.speed_target_rpm, self.load_torque_nm, self.dc_bus_voltage_v, self.current_limit_a)
        DynamicOperatingRequest(0, self.speed_target_rpm, self.load_torque_nm, self.dc_bus_voltage_v,
                                self.current_limit_a, self.deadline_s, hold_time_s=self.hold_time_s)
        if (not all(isfinite(v) for v in (self.simulation_duration_s, self.load_step_time_s, self.simulation_dt_s))
                or self.simulation_dt_s <= 0 or self.simulation_duration_s <= 0
                or not 0 <= self.load_step_time_s < self.simulation_duration_s
                or min(self.simulation_duration_s-self.load_step_time_s, self.deadline_s) < 2*self.simulation_dt_s):
            raise ValueError("workflow.invalid_simulation_timing")


@dataclass(frozen=True)
class RunMetadata:
    version: str
    release_status: str
    repository_revision: str | None
    repository_dirty: bool | None
    generated_at_utc: str


@dataclass(frozen=True)
class MeasurementRecord:
    stage: Stage
    number: int
    config: object
    measurements: object
    measurement_failure: str | None = None


@dataclass(frozen=True)
class CurrentControllerConstants:
    kp_d: float
    ki_d: float
    kp_q: float
    ki_q: float
    anti_windup_gain: float
    dc_bus_voltage_v: float
    voltage_limit_v: float


@dataclass(frozen=True)
class SpeedControllerConstants:
    kp: float
    ki: float
    torque_constant_nm_per_a: float
    iq_limit_a: float


@dataclass(frozen=True)
class ControllerConstants:
    current: CurrentControllerConstants
    speed: SpeedControllerConstants


@dataclass(frozen=True)
class ControlValidation:
    trace: Mapping
    metrics: Mapping


@dataclass(frozen=True)
class SimulationEvaluation:
    truth: MotorConfiguration
    parameter_absolute_error_percent: Mapping[str, float]


@dataclass(frozen=True)
class EngineeringWorkflowResult:
    config: EngineeringWorkflowConfig
    metadata: RunMetadata
    nonidealities: DriveNonidealities
    commissioning: FullCommissioningResult | None
    quality: CommissioningQuality
    attempts: tuple[AttemptRecord, ...]
    measurement_records: tuple[MeasurementRecord, ...]
    supervisor: SupervisorResult | None
    controller_parameters: MotorConfiguration
    controller_constants: ControllerConstants
    steady_feasibility: object | None
    dynamic_feasibility: object | None
    control: ControlValidation | None
    firmware_config: FirmwareConfig | None
    simulation_evaluation: SimulationEvaluation
    warnings: tuple[str, ...]

    @property
    def status(self):
        return "FULL ACCEPTED" if self.quality.accepted else "REJECTED"

    @property
    def firmware_available(self):
        return self.quality.accepted and self.firmware_config is not None


def repository_metadata():
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return RunMetadata(__version__, RELEASE_STATUS, revision, dirty, datetime.now(timezone.utc).isoformat())


def controller_constants(parameters, bus, iq_limit):
    """Inspect existing constructors; no independent gain equations."""
    current = CurrentFOCController(parameters, dc_bus_voltage=bus)
    speed = SpeedController(parameters, iq_limit=iq_limit)
    return ControllerConstants(CurrentControllerConstants(current.pi_d.kp, current.pi_d.ki,
        current.pi_q.kp, current.pi_q.ki, current.anti_windup_gain, bus, current.voltage_limit),
        SpeedControllerConstants(speed.kp, speed.ki, speed.kt, iq_limit))


def _record_attempt(stage, config, estimate, quality):
    return AttemptRecord(stage, 1, config, estimate is not None, estimate, quality, _snapshot(estimate, stage),
                         "accepted" if quality.accepted else "terminal", None, None)


def _one_shot(locked, rotating, mechanical, prior, ec, rc, mc):
    electrical = commission_from_measurements(locked(ec), rotating(rc), prior.pole_pairs)
    e = electrical.electrical
    standstill_quality = electrical.quality if e is None else _standstill_quality(e, prior.pole_pairs, QualityPolicy())
    attempts = [_record_attempt(Stage.STANDSTILL, ec, e, standstill_quality)]
    if e is not None:
        checks = tuple(c for c in electrical.quality.checks if c.name.startswith("rotating."))
        flux_quality = (electrical.quality if electrical.flux is None else
            CommissioningQuality(not any(not c.passed for c in checks), tuple(c.name for c in checks if not c.passed), checks))
        attempts.append(_record_attempt(Stage.ROTATING, rc, electrical.flux, flux_quality))
    try:
        data = mechanical(mc, electrical.retuned_controller_parameters(prior)) if electrical.quality.accepted else None
    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        quality = _estimator_failure(Stage.MECHANICAL, exc)
        attempts.append(_record_attempt(Stage.MECHANICAL, mc, None, quality))
        return FullCommissioningResult(electrical, MechanicalCommissioningResult(None, quality)), tuple(attempts)
    full = complete_commissioning(electrical, data)
    if data is not None:
        attempts.append(_record_attempt(Stage.MECHANICAL, mc, full.mechanical.estimate, full.mechanical.quality))
    return full, tuple(attempts)


def run_engineering_workflow(config=EngineeringWorkflowConfig()):
    """Compute a new run. Rejection never starts commissioned operation/export.

    M17 presets are imported unchanged. Operating drift applies ONLY in the
    simulation's existing operation boundary; mechanical load is known zero.
    Metadata does not seed any computation. No historical results are inputs.
    """
    if not isinstance(config, EngineeringWorkflowConfig):
        raise TypeError("workflow.requires_configuration")
    errors = next(s.errors for s in scenarios() if s.name == config.scenario)
    commissioning_errors = errors if config.exposure != "operation_only" else DriveNonidealities()
    operation_errors = errors if config.exposure != "commissioning_only" else DriveNonidealities()
    plant, prior = config.simulation_truth.parameters(), config.prior_assumptions.parameters()
    ec = replace(config.standstill, seed=config.seed, dc_bus_voltage_v=config.dc_bus_voltage_v)
    rc = replace(config.rotating, seed=config.seed+1, dc_bus_voltage_v=config.dc_bus_voltage_v)
    mc = replace(config.mechanical, seed=config.seed+2, dc_bus_voltage_v=config.dc_bus_voltage_v)
    # Record the RESOLVED provider inputs, not obsolete dataclass defaults.
    config = replace(config, standstill=ec, rotating=rc, mechanical=mc)
    records = []

    def acquire(stage, excitation, provider):
        number = sum(r.stage == stage for r in records)+1
        try:
            data = provider()
        except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            records.append(MeasurementRecord(stage, number, excitation, None, str(exc)))
            raise
        records.append(MeasurementRecord(stage, number, excitation, data))
        return data

    def locked(cfg):
        return acquire(Stage.STANDSTILL, cfg, lambda: simulate_locked_rotor_measurements(plant, cfg, commissioning_errors))

    def rotating(cfg):
        return acquire(Stage.ROTATING, cfg, lambda: simulate_driven_rotor_measurements(plant, cfg, commissioning_errors))

    def mechanical(cfg, controller):
        return acquire(Stage.MECHANICAL, cfg, lambda: simulate_mechanical_measurements(plant, controller, cfg, commissioning_errors).measurements)

    supervisor = full = None
    attempts = ()
    try:
        if config.mode == "adaptive":
            supervisor = run_adaptive_commissioning(locked, rotating, mechanical, prior,
                standstill_config=ec, rotating_config=rc, mechanical_config=mc)
            full, attempts = supervisor.full_commissioning, supervisor.attempts
            quality = full.quality if supervisor.accepted else attempts[-1].quality
        else:
            full, attempts = _one_shot(locked, rotating, mechanical, prior, ec, rc, mc)
            quality = full.quality
    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        # Provider/config failures can occur before the estimator is invoked.
        # Expose them; do not present them as a successful fit or gate decision.
        quality = CommissioningQuality(False, ("workflow.measurement_or_configuration_failure: "+str(exc),),
                                       estimator_failure=str(exc))
    parameters = full.retuned_controller_parameters(prior) if quality.accepted else prior
    steady = dynamic = control = firmware = None
    warnings = ["Mechanical commissioning assumes explicitly known zero external load.",
                "M16 prediction uses constant load from t=0; closed-loop validation uses the configured load step."]
    if quality.accepted:
        request = OperatingPointRequest(config.speed_target_rpm, config.load_torque_nm, config.dc_bus_voltage_v, config.current_limit_a)
        dynamic_request = DynamicOperatingRequest(0, config.speed_target_rpm, config.load_torque_nm,
            config.dc_bus_voltage_v, config.current_limit_a, config.deadline_s, hold_time_s=config.hold_time_s)
        # Keep post-acceptance failures separate from identification quality.
        for stage in ("steady", "dynamic", "control", "firmware"):
            try:
                if stage == "steady":
                    steady = assess_operating_point(full, request)
                elif stage == "dynamic":
                    dynamic = assess_dynamic_operating_point(full, dynamic_request,
                        DynamicAnalysisConfig(simulation_dt_s=config.simulation_dt_s))
                elif stage == "control":
                    trace = run_speed_foc_simulation(plant_params=plant, controller_params=prior,
                        commissioning_result=full, dt=config.simulation_dt_s, simulation_time=config.simulation_duration_s,
                        speed_ref_rpm=config.speed_target_rpm, load_step_time=config.load_step_time_s,
                        load_step_torque=config.load_torque_nm, dc_bus_voltage=config.dc_bus_voltage_v,
                        current_limit_a=config.current_limit_a, nonidealities=operation_errors)
                    metrics = operation_metrics(trace)
                    trace = {k: v for k, v in trace.items() if k not in ("plant_params", "controller_params")}
                    for value in trace.values():
                        if isinstance(value, np.ndarray): value.setflags(write=False)
                    control = ControlValidation(MappingProxyType(trace), MappingProxyType(metrics))
                else:
                    firmware = build_firmware_config(full, dc_bus_voltage_v=config.dc_bus_voltage_v, iq_limit_a=config.current_limit_a)
            except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
                warnings.append(f"workflow.{stage}_unavailable: {exc}")
    else:
        warnings.append("Rejected commissioning: prior parameters retained; commissioned operation and firmware export unavailable.")

    # POST-HOC EVALUATION ONLY: never feeds a gate, supervisor or retuning call.
    estimates = {}
    for attempt in attempts:
        if attempt.estimate is not None:
            for name in PARAMETER_NAMES[:-1]:
                if hasattr(attempt.estimate, name): estimates[name] = getattr(attempt.estimate, name)
    errors_percent = {n: abs(v-getattr(plant, n))/abs(getattr(plant, n))*100
                      for n, v in estimates.items() if getattr(plant, n) != 0}
    if not errors.is_ideal:
        warnings.append("Configured M17 impairments are simulation stress/error models, not hardware specifications.")
    if control is not None and control.metrics.get("control_speed_rmse_rpm", float("inf")) is not None:
        if control.metrics["control_speed_rmse_rpm"] <= 10 and any(v > 10 for v in errors_percent.values()):
            warnings.append("This run has good speed tracking but >10% post-hoc parameter error: speed tracking does not prove accurate commissioning.")
    return EngineeringWorkflowResult(config, repository_metadata(), errors, full, quality, attempts, tuple(records),
        supervisor, MotorConfiguration.from_parameters(parameters), controller_constants(parameters, config.dc_bus_voltage_v, config.current_limit_a),
        steady, dynamic, control, firmware, SimulationEvaluation(config.simulation_truth, MappingProxyType(errors_percent)), tuple(warnings))


def export_firmware_configuration(result, path):
    """Recheck full acceptance at the export boundary; never fall back to prior."""
    if not result.quality.accepted or result.commissioning is None:
        raise CommissioningRejectedError(result.quality)
    if not result.firmware_available:
        raise ValueError("workflow.firmware_configuration_unavailable")
    config = build_firmware_config(result.commissioning, dc_bus_voltage_v=result.config.dc_bus_voltage_v,
                                  iq_limit_a=result.config.current_limit_a)
    return export_c_header(config, path, provenance=f"SIMULATED accepted full commissioning; project {__version__}; seed {result.config.seed}; scenario {result.config.scenario}.")
