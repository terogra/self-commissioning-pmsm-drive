import numpy as np
import matplotlib.pyplot as plt

from src.motor import PMSMModel, PMSMParameters
from src.foc import CurrentFOCController
from src.speed_control import SpeedController
from src.simulation import rk4_step


def rpm_to_rad_per_sec(rpm):
    return rpm * 2.0 * np.pi / 60.0


def rad_per_sec_to_rpm(omega):
    return omega * 60.0 / (2.0 * np.pi)


def main():

    # Motor model
    params = PMSMParameters()
    motor = PMSMModel(params)

    # Inner current-control loop
    current_controller = CurrentFOCController(
        params,
        current_bandwidth_hz=300.0
    )

    # Outer speed-control loop
    speed_controller = SpeedController(
        params,
        natural_frequency_hz=10.0,
        damping_ratio=1.0,
        iq_limit=5.0
    )

    # Simulation settings
    dt = 20e-6
    simulation_time = 0.6

    time = np.arange(
        0.0,
        simulation_time,
        dt
    )

    # State:
    # [id, iq, omega_m, theta_e]
    state = np.zeros(4)

    # Desired motor speed
    speed_ref_rpm = 1000.0

    omega_ref = rpm_to_rad_per_sec(
        speed_ref_rpm
    )

    # FOC flux-axis current reference
    id_ref = 0.0

    # Logging arrays
    rpm_history = np.zeros(len(time))
    id_history = np.zeros(len(time))
    iq_history = np.zeros(len(time))
    iq_ref_history = np.zeros(len(time))
    torque_history = np.zeros(len(time))
    load_history = np.zeros(len(time))

    for k, t in enumerate(time):

        i_d = state[0]
        i_q = state[1]
        omega_m = state[2]

        # Apply load disturbance after 0.30 s
        if t < 0.30:
            load_torque = 0.0
        else:
            load_torque = 0.05

        # Outer speed loop
        iq_ref = speed_controller.update(
            omega_ref=omega_ref,
            omega_measured=omega_m,
            dt=dt
        )

        # Inner current-control loops
        v_d, v_q = current_controller.update(
            id_ref=id_ref,
            iq_ref=iq_ref,
            i_d=i_d,
            i_q=i_q,
            omega_m=omega_m,
            dt=dt
        )

        # PMSM model integration
        state = rk4_step(
            motor,
            state,
            v_d,
            v_q,
            load_torque,
            dt
        )

        # Record signals
        rpm_history[k] = rad_per_sec_to_rpm(
            state[2]
        )

        id_history[k] = state[0]
        iq_history[k] = state[1]
        iq_ref_history[k] = iq_ref

        torque_history[k] = (
            motor.electromagnetic_torque(
                state[0],
                state[1]
            )
        )

        load_history[k] = load_torque

    # Final values
    print(
        f"Final speed: "
        f"{rpm_history[-1]:.2f} rpm"
    )

    print(
        f"Final speed error: "
        f"{speed_ref_rpm - rpm_history[-1]:.4f} rpm"
    )

    print(
        f"Final id: "
        f"{id_history[-1]:.4f} A"
    )

    print(
        f"Final iq: "
        f"{iq_history[-1]:.4f} A"
    )

    print(
        f"Final iq reference: "
        f"{iq_ref_history[-1]:.4f} A"
    )

    # Speed plot
    plt.figure()

    plt.plot(
        time,
        rpm_history,
        label="Measured speed"
    )

    plt.axhline(
        speed_ref_rpm,
        linestyle="--",
        label="Speed reference"
    )

    plt.axvline(
        0.30,
        linestyle=":",
        label="Load applied"
    )

    plt.xlabel("Time [s]")
    plt.ylabel("Speed [rpm]")
    plt.title("Closed-Loop PMSM Speed Control")
    plt.grid()
    plt.legend()

    # iq plot
    plt.figure()

    plt.plot(
        time,
        iq_history,
        label="iq"
    )

    plt.plot(
        time,
        iq_ref_history,
        linestyle="--",
        label="iq reference"
    )

    plt.xlabel("Time [s]")
    plt.ylabel("Current [A]")
    plt.title("Torque-Producing Current")
    plt.grid()
    plt.legend()

    # id plot
    plt.figure()

    plt.plot(
        time,
        id_history
    )

    plt.axhline(
        0.0,
        linestyle="--"
    )

    plt.xlabel("Time [s]")
    plt.ylabel("id [A]")
    plt.title("Flux-Axis Current")
    plt.grid()

    # Torque plot
    plt.figure()

    plt.plot(
        time,
        torque_history,
        label="Motor torque"
    )

    plt.plot(
        time,
        load_history,
        linestyle="--",
        label="Load torque"
    )

    plt.xlabel("Time [s]")
    plt.ylabel("Torque [N.m]")
    plt.title("Motor Torque and Load")
    plt.grid()
    plt.legend()

    plt.show()


if __name__ == "__main__":
    main()