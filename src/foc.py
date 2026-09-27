import numpy as np

from src.controllers import PIController
from src.motor import PMSMParameters


class CurrentFOCController:
    def __init__(
        self,
        params: PMSMParameters,
        current_bandwidth_hz: float = 300.0,
        dc_bus_voltage: float | None = 48.0,
        anti_windup_gain: float | None = None,
    ):
        self.params = params

        if dc_bus_voltage is not None and (
            not np.isfinite(dc_bus_voltage) or dc_bus_voltage <= 0
        ):
            raise ValueError("dc_bus_voltage must be positive and finite, or None")
        self.dc_bus_voltage = dc_bus_voltage
        # Inscribed-circle limit for linear space-vector PWM; dq voltage is
        # the phase-neutral fundamental peak in the amplitude-invariant frame.
        self.voltage_limit = (
            dc_bus_voltage / np.sqrt(3.0) if dc_bus_voltage is not None else None
        )

        omega_c = 2.0 * np.pi * current_bandwidth_hz
        if anti_windup_gain is not None and (
            not np.isfinite(anti_windup_gain) or anti_windup_gain < 0
        ):
            raise ValueError("anti_windup_gain must be nonnegative and finite")
        self.anti_windup_gain = omega_c if anti_windup_gain is None else anti_windup_gain
        self.voltage_saturated = False
        self.voltage_magnitude = 0.0
        self.requested_voltage_magnitude = 0.0

        kp_d = params.Ld * omega_c
        ki_d = params.Rs * omega_c

        kp_q = params.Lq * omega_c
        ki_q = params.Rs * omega_c

        self.pi_d = PIController(kp_d, ki_d)
        self.pi_q = PIController(kp_q, ki_q)

    def update(
        self,
        id_ref: float,
        iq_ref: float,
        i_d: float,
        i_q: float,
        omega_m: float,
        dt: float
    ):
        p = self.params

        omega_e = p.pole_pairs * omega_m

        error_d = id_ref - i_d
        error_q = iq_ref - i_q

        vd_pi = self.pi_d.update(error_d, dt)
        vq_pi = self.pi_q.update(error_q, dt)

        # Decoupling compensation
        v_d = vd_pi - omega_e * p.Lq * i_q

        v_q = (
            vq_pi
            + omega_e * (p.Ld * i_d + p.psi_f)
        )

        self.requested_voltage_magnitude = float(np.hypot(v_d, v_q))
        self.voltage_saturated = (
            self.voltage_limit is not None
            and self.requested_voltage_magnitude > self.voltage_limit
        )
        if self.voltage_saturated:
            scale = self.voltage_limit / self.requested_voltage_magnitude
            applied_v_d, applied_v_q = v_d * scale, v_q * scale
            self.pi_d.track_output(applied_v_d, v_d, dt, self.anti_windup_gain)
            self.pi_q.track_output(applied_v_q, v_q, dt, self.anti_windup_gain)
            v_d, v_q = applied_v_d, applied_v_q

        self.voltage_magnitude = float(np.hypot(v_d, v_q))
        return v_d, v_q
