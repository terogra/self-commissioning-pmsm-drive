import numpy as np
import matplotlib.pyplot as plt

from src.foc import CurrentFOCController
from src.motor import PMSMModel, PMSMParameters
from src.simulation import rk4_step


LOAD_TORQUES = [0.00, 0.05, 0.10]


def run_foc(load_torque):
    params = PMSMParameters()
    motor = PMSMModel(params)

    controller = CurrentFOCController(
        params,
        current_bandwidth_hz=300.0
    )

    dt = 20e-6
    simulation_time = 0.15

    time = np.arange(0.0, simulation_time, dt)

    state = np.zeros(4)

    id_ref = 0.0
    iq_ref = 1.0

    for _ in time:
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

        state = rk4_step(
            motor,
            state,
            v_d,
            v_q,
            load_torque,
            dt
        )

    i_d = state[0]
    i_q = state[1]
    omega_m = state[2]

    rpm = omega_m * 60.0 / (2.0 * np.pi)

    return i_d, i_q, rpm


def main():
    speeds = []

    print()
    print(
        "Load [Nm] | Final id [A] | "
        "Final iq [A] | Speed [rpm]"
    )
    print("-" * 60)

    for load in LOAD_TORQUES:
        i_d, i_q, rpm = run_foc(load)

        speeds.append(rpm)

        print(
            f"{load:8.2f} | "
            f"{i_d:12.4f} | "
            f"{i_q:12.4f} | "
            f"{rpm:11.2f}"
        )

    assert all(
        abs(run_foc(load)[0]) < 1e-3
        for load in LOAD_TORQUES
    )

    assert all(
        abs(run_foc(load)[1] - 1.0) < 1e-3
        for load in LOAD_TORQUES
    )

    assert speeds[0] > speeds[1] > speeds[2]

    print()
    print("PASS: FOC load-sweep validation successful.")

    plt.figure()
    plt.plot(
        LOAD_TORQUES,
        speeds,
        marker="o"
    )
    plt.xlabel("Load Torque [N.m]")
    plt.ylabel("Speed at 0.15 s [rpm]")
    plt.title("FOC Response Under Increasing Load")
    plt.grid()
    plt.show()


if __name__ == "__main__":
    main()