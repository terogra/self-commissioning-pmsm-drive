"""Free-rotor, known-zero-load current plateaus for mechanical commissioning."""

from dataclasses import dataclass

import numpy as np

from src.foc import CurrentFOCController
from src.identification_quality import MeasurementNoise
from src.mechanical_identification import MechanicalMeasurements
from src.motor import PMSMModel
from src.simulation import rk4_step


@dataclass(frozen=True)
class MechanicalExcitationConfig:
    # Repeat the pattern so both chronological halves contain acceleration/coast.
    iq_plateaus_a: tuple[float, ...] = (0.8, 0.0, 0.4, -0.4, 0.0) * 2
    plateau_duration_s: float = 0.25
    control_dt_s: float = 40e-6
    sample_dt_s: float = 1e-3
    dc_bus_voltage_v: float = 48.0
    current_reference_limit_a: float = 1.0
    current_noise_std_a: float = 0.01
    speed_noise_std_rad_s: float = 0.05
    seed: int = 701


@dataclass(frozen=True)
class MechanicalExcitationRecord:
    measurements: MechanicalMeasurements
    iq_reference_a: np.ndarray
    applied_voltage_magnitude_v: np.ndarray
    saturation_fraction: float


def simulate_mechanical_measurements(plant_params, controller_params, config=MechanicalExcitationConfig(), nonidealities=None):
    """Simulate real dynamics; expose samples only, never hidden Te/J/B.

    Current references are bounded and applied through the existing voltage-limited
    FOC. Optional deterministic signal-chain errors affect feedback/actuation;
    Gaussian noise is added only to the commissioning record.
    The constant external load is explicitly zero. Limits here are simulation
    constraints, not a hardware safety procedure.
    """
    if (not config.iq_plateaus_a or any(not np.isfinite(v) for v in config.iq_plateaus_a)
            or any(not np.isfinite(v) or v <= 0 for v in (
                config.plateau_duration_s, config.control_dt_s, config.sample_dt_s,
                config.current_reference_limit_a, config.dc_bus_voltage_v))):
        raise ValueError("Invalid mechanical excitation configuration")
    noise = MeasurementNoise(config.current_noise_std_a, speed_std_rad_s=config.speed_noise_std_rad_s)
    if max(abs(v) for v in config.iq_plateaus_a) > config.current_reference_limit_a:
        raise ValueError("Mechanical current reference exceeds configured limit")
    stride = round(config.sample_dt_s / config.control_dt_s)
    phase_steps = round(config.plateau_duration_s / config.control_dt_s)
    if (stride < 1 or phase_steps < 1
            or not np.isclose(stride * config.control_dt_s, config.sample_dt_s)
            or not np.isclose(phase_steps * config.control_dt_s, config.plateau_duration_s)
            or phase_steps % stride):
        raise ValueError("Sample/plateau periods must be integer multiples of control/sample steps")
    steps = phase_steps * len(config.iq_plateaus_a)
    motor = PMSMModel(plant_params)
    controller = CurrentFOCController(controller_params, dc_bus_voltage=config.dc_bus_voltage_v)
    state = np.zeros(4)
    samples, refs, voltages = [state[:3].copy()], [config.iq_plateaus_a[0]], [0.0]
    saturated = 0
    active = nonidealities is not None and nonidealities.has_signal_errors
    if active:
        from src.drive_nonidealities import apply_voltage, measure_current, delayed_samples, FeedbackDelay
        feedback_delay = FeedbackDelay(nonidealities.timing.feedback_delay_steps)
        samples[0][:2] = measure_current(state[:2], state[3], nonidealities)
    for k in range(steps):
        ref = config.iq_plateaus_a[k // phase_steps]
        feedback, command_angle = state[:3], state[3]
        if active:
            measured = measure_current(state[:2], state[3], nonidealities)
            delayed = feedback_delay.sample((*measured, state[2],
                                             state[3]+nonidealities.frame.electrical_angle_bias_rad))
            feedback, command_angle = delayed[:3], delayed[3]
        vd, vq = controller.update(0.0, ref, *feedback, config.control_dt_s)
        if active:
            applied = apply_voltage((vd, vq), state[:2], state[3], command_angle,
                                    config.dc_bus_voltage_v, nonidealities)
            vd, vq = applied.terminal_d_v, applied.terminal_q_v
        state = rk4_step(motor, state, vd, vq, 0.0, config.control_dt_s)
        saturated += int(controller.voltage_saturated)
        if (k+1) % stride == 0:
            recorded = state[:3].copy()
            if active:
                recorded[:2] = measure_current(state[:2], state[3], nonidealities)
            samples.append(recorded)
            refs.append(ref)
            voltages.append(float(np.hypot(vd, vq)) if active else controller.voltage_magnitude)
    samples = np.asarray(samples)
    if active:
        # Record alignment delays dq currents only; speed/time remain current.
        samples[:, :2] = delayed_samples(samples[:, :2], nonidealities.timing.record_current_delay_samples)
    if not np.all(np.isfinite(samples)):
        raise ValueError("Mechanical excitation produced nonfinite samples")
    rng = np.random.default_rng(config.seed)
    data = MechanicalMeasurements(
        np.arange(len(samples)) * config.sample_dt_s,
        samples[:, 0] + rng.normal(0, noise.current_std_a, len(samples)),
        samples[:, 1] + rng.normal(0, noise.current_std_a, len(samples)),
        samples[:, 2] + rng.normal(0, noise.speed_std_rad_s, len(samples)),
        known_load_torque_nm=0.0, noise=noise,
    )
    return MechanicalExcitationRecord(data, np.asarray(refs), np.asarray(voltages), saturated / steps)
