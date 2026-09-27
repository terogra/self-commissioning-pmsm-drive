import matplotlib.pyplot as plt
import numpy as np

from src.foc import CurrentFOCController
from src.motor import PMSMModel, PMSMParameters
from src.simulation import rk4_step


def main():

    params = PMSMParameters()
    motor = PMSMModel(params)

    controller = CurrentFOCController(
        params,
        current_bandwidth_hz=300.0
    )

    dt = 20e-6
    simulation_time = 0.15

    time = np.arange(
        0.0,
        simulation_time,
        dt
    )

    state = np.zeros(4)

    id_ref = 0.0
    iq_ref = 1.0

    load_torque = 0.10

    states = np.zeros(
        (len(time), 4)
    )

    vd_history = np.zeros(len(time))
    vq_history = np.zeros(len(time))
    torque_history = np.zeros(len(time))

    for k in range(len(time)):

        states[k] = state

        i_d = state[0]
        i_q = state[1]
        omega_m = state[2]

        v_d, v_q = controller.update(
            id_ref=id_ref,
            iq_ref=iq_ref,
            i_d=i_d,
            i_q=i_q,
            omega_m=omega_m,
            dt=dt
        )

        vd_history[k] = v_d
        vq_history[k] = v_q

        torque_history[k] = (
            motor.electromagnetic_torque(
                i_d,
                i_q
            )
        )

        state = rk4_step(
            motor,
            state,
            v_d,
            v_q,
            load_torque,
            dt
        )

    i_d = states[:, 0]
    i_q = states[:, 1]
    omega_m = states[:, 2]

    rpm = (
        omega_m
        * 60.0
        / (2.0 * np.pi)
    )

    print(f"Final id: {i_d[-1]:.4f} A")
    print(f"Final iq: {i_q[-1]:.4f} A")
    print(f"Final speed: {rpm[-1]:.2f} rpm")

    plt.figure()
    plt.plot(time, i_d, label="id")
    plt.axhline(
        id_ref,
        linestyle="--",
        label="id reference"
    )
    plt.xlabel("Time [s]")
    plt.ylabel("Current [A]")
    plt.title("d-axis Current Control")
    plt.grid()
    plt.legend()

    plt.figure()
    plt.plot(time, i_q, label="iq")
    plt.axhline(
        iq_ref,
        linestyle="--",
        label="iq reference"
    )
    plt.xlabel("Time [s]")
    plt.ylabel("Current [A]")
    plt.title("q-axis Current Control")
    plt.grid()
    plt.legend()

    plt.figure()
    plt.plot(time, rpm)
    plt.xlabel("Time [s]")
    plt.ylabel("Speed [rpm]")
    plt.title(
        "Mechanical Speed with Current-Control FOC"
    )
    plt.grid()

    plt.figure()
    plt.plot(time, torque_history)
    plt.xlabel("Time [s]")
    plt.ylabel("Torque [N.m]")
    plt.title("Electromagnetic Torque")
    plt.grid()

    plt.figure()
    plt.plot(time, vd_history, label="vd")
    plt.plot(time, vq_history, label="vq")
    plt.xlabel("Time [s]")
    plt.ylabel("Voltage [V]")
    plt.title("FOC Voltage Commands")
    plt.grid()
    plt.legend()

    plt.show()


if __name__ == "__main__":
    main()