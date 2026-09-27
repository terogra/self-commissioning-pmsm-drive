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
    """
    One numerical integration step using
    fourth-order Runge-Kutta (RK4).
    """

    k1 = motor.derivatives(
        state,
        v_d,
        v_q,
        load_torque
    )

    k2 = motor.derivatives(
        state + 0.5 * dt * k1,
        v_d,
        v_q,
        load_torque
    )

    k3 = motor.derivatives(
        state + 0.5 * dt * k2,
        v_d,
        v_q,
        load_torque
    )

    k4 = motor.derivatives(
        state + dt * k3,
        v_d,
        v_q,
        load_torque
    )

    return state + (dt / 6.0) * (
        k1 + 2.0 * k2 + 2.0 * k3 + k4
    )


def main():

    # ---------------------------------
    # Motor parameters
    # ---------------------------------

    params = PMSMParameters()
    motor = PMSMModel(params)

    # ---------------------------------
    # Simulation settings
    # ---------------------------------

    dt = 20e-6
    simulation_time = 0.5

    time = np.arange(
        0.0,
        simulation_time,
        dt
    )

    # State:
    # [id, iq, omega_m, theta_e]

    state = np.array([
        0.0,
        0.0,
        0.0,
        0.0
    ])

    # Open-loop dq voltages
    v_d = 0.0
    v_q = 8.0

    # No mechanical load for first test
    load_torque = 0.00

    states = np.zeros(
        (len(time), 4)
    )

    torque = np.zeros(
        len(time)
    )

    # ---------------------------------
    # Simulation loop
    # ---------------------------------

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

    # ---------------------------------
    # Extract results
    # ---------------------------------

    i_d = states[:, 0]
    i_q = states[:, 1]
    omega_m = states[:, 2]

    rpm = (
        omega_m
        * 60.0
        / (2.0 * np.pi)
    )

    # ---------------------------------
    # Plot results
    # ---------------------------------

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

    print(f"Steady-state id: {i_d[-1]:.4f} A")
    print(f"Steady-state iq: {i_q[-1]:.4f} A")
    print(f"Steady-state speed: {rpm[-1]:.2f} rpm")
    print(f"Steady-state torque: {torque[-1]:.4f} N.m")

    plt.show()


if __name__ == "__main__":
    main()