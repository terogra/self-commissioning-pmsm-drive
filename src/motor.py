from dataclasses import dataclass
import numpy as np


@dataclass
class PMSMParameters:
    Rs: float = 0.4          # Stator resistance [ohm]
    Ld: float = 1.0e-3      # d-axis inductance [H]
    Lq: float = 1.0e-3      # q-axis inductance [H]
    psi_f: float = 0.025     # Permanent magnet flux linkage [Wb]
    pole_pairs: int = 4      # Number of pole pairs
    J: float = 2.0e-4        # Rotor inertia [kg*m^2]
    B: float = 1.0e-4        # Viscous friction [N*m*s/rad]


class PMSMModel:
    def __init__(self, params: PMSMParameters):
        self.p = params

    def electromagnetic_torque(self, i_d: float, i_q: float) -> float:
        p = self.p

        torque = 1.5 * p.pole_pairs * (
            p.psi_f * i_q
            + (p.Ld - p.Lq) * i_d * i_q
        )

        return torque

    def derivatives(
        self,
        state: np.ndarray,
        v_d: float,
        v_q: float,
        load_torque: float
    ) -> np.ndarray:

        i_d, i_q, omega_m, theta_e = state

        p = self.p

        # Electrical speed
        omega_e = p.pole_pairs * omega_m

        # Electrical dynamics
        di_d = (
            v_d
            - p.Rs * i_d
            + omega_e * p.Lq * i_q
        ) / p.Ld

        di_q = (
            v_q
            - p.Rs * i_q
            - omega_e * (p.Ld * i_d + p.psi_f)
        ) / p.Lq

        # Electromagnetic torque
        torque_e = self.electromagnetic_torque(i_d, i_q)

        # Mechanical dynamics
        domega_m = (
            torque_e
            - load_torque
            - p.B * omega_m
        ) / p.J

        # Electrical rotor angle
        dtheta_e = omega_e

        return np.array([
            di_d,
            di_q,
            domega_m,
            dtheta_e
        ])