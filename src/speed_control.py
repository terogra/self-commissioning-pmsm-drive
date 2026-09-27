import numpy as np

from src.controllers import PIController
from src.motor import PMSMParameters


class SpeedController:
    def __init__(
        self,
        params: PMSMParameters,
        natural_frequency_hz: float = 10.0,
        damping_ratio: float = 1.0,
        iq_limit: float = 5.0
    ):
        self.params = params

        # PMSM torque constant
        self.kt = (
            1.5
            * params.pole_pairs
            * params.psi_f
        )

        omega_n = 2.0 * np.pi * natural_frequency_hz

        kp = (
            2.0
            * damping_ratio
            * omega_n
            * params.J
            - params.B
        ) / self.kt

        ki = (
            omega_n ** 2
            * params.J
        ) / self.kt

        self.pi = PIController(
            kp=kp,
            ki=ki,
            output_min=-iq_limit,
            output_max=iq_limit
        )

        self.kp = kp
        self.ki = ki

    def update(
        self,
        omega_ref: float,
        omega_measured: float,
        dt: float
    ) -> float:

        error = omega_ref - omega_measured

        return self.pi.update(
            error,
            dt
        )