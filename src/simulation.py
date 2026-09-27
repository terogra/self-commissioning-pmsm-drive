import numpy as np
import matplotlib.pyplot as plt

from src.motor import PMSMModel, PMSMParameters


def rk4_step(
    motor,
    state,
    v_d,
    v_q,
    load_torque,
    dt
):
    """One fourth-order Runge-Kutta integration step."""

    k1 = motor.derivatives(
        state, v_d, v_q, load_torque
    )

    k2 = motor.derivatives(
        state + 0.5 * dt * k1,
        v_d, v_q, load_torque
    )

    k3 = motor.derivatives(
        state + 0.5 * dt * k2,
        v_d, v_q, load_torque
    )

    k4 = motor.derivatives(
        state + dt * k3,
        v_d, v_q, load_torque
    )

    return state + (dt / 6.0) * (
        k1 + 2.0 * k2 + 2.0 * k3 + k4
    )


def steady_state_mean(signal, fraction=0.10):
    """
    Return the mean value over the final fraction
    of the simulation.
    """
    start_index = int(
        len(signal) * (1.0 - fraction)
    )

    return np.mean(signal[start_index:])


def run_open_loop_simulation(
    load_torque=0.0,
    v_d=0.0,
    v_q=8.0,
    dt=20e-6,
    simulation_time=0.5
):
    """
    Run an open-loop PMSM simulation.

    Returns simulation signals and parameters.
    """

    params = PMSMParameters()
    motor = PMSMModel(params)

    time = np.arange(
        0.0,
        simulation_time,
        dt
    )

    # State vector:
    # [id, iq, omega_m, theta_e]
    state = np.zeros(4)

    states = np.zeros(
        (len(time), 4)
    )

    torque = np.zeros(
        len(time)
    )

    for k in range(len(time)):

        states[k] = state

        torque[k] = motor.electromagnetic_torque(
            state[0],
            state[1]
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

    return {
        "time": time,
        "id": i_d,
        "iq": i_q,
        "omega_m": omega_m,
        "rpm": rpm,
        "torque": torque,
        "params": params
    }


def main():

    result = run_open_loop_simulation(
        load_torque=0.0
    )

    time = result["time"]
    i_d = result["id"]
    i_q = result["iq"]
    rpm = result["rpm"]
    torque = result["torque"]

    print(
        f"Steady-state id: "
        f"{steady_state_mean(i_d):.4f} A"
    )

    print(
        f"Steady-state iq: "
        f"{steady_state_mean(i_q):.4f} A"
    )

    print(
        f"Steady-state speed: "
        f"{steady_state_mean(rpm):.2f} rpm"
    )

    print(
        f"Steady-state torque: "
        f"{steady_state_mean(torque):.4f} N.m"
    )

    plt.figure()
    plt.plot(time, i_d)
    plt.xlabel("Time [s]")
    plt.ylabel("d-axis Current [A]")
    plt.title("PMSM d-axis Current")
    plt.grid()

    plt.figure()
    plt.plot(time, i_q)
    plt.xlabel("Time [s]")
    plt.ylabel("q-axis Current [A]")
    plt.title("PMSM q-axis Current")
    plt.grid()

    plt.figure()
    plt.plot(time, rpm)
    plt.xlabel("Time [s]")
    plt.ylabel("Speed [rpm]")
    plt.title("PMSM Mechanical Speed")
    plt.grid()

    plt.figure()
    plt.plot(time, torque)
    plt.xlabel("Time [s]")
    plt.ylabel("Torque [N.m]")
    plt.title("Electromagnetic Torque")
    plt.grid()

    plt.show()


if __name__ == "__main__":
    main()