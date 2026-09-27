import numpy as np

from src.controllers import PIController
from src.motor import PMSMParameters


class CurrentFOCController:
    def __init__(
        self,
        params: PMSMParameters,
        current_bandwidth_hz: float = 300.0
    ):
        self.params = params

        omega_c = 2.0 * np.pi * current_bandwidth_hz

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

        return v_d, v_q