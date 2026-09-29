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


def run_speed_foc_simulation(
    plant_params=None,
    controller_params=None,
    dt=20e-6,
    simulation_time=0.6,
    speed_ref_rpm=1000.0,
    load_step_time=0.30,
    load_step_torque=0.05,
    dc_bus_voltage=48.0,
    commissioning_result=None,
    current_limit_a=5.0,
):
    """Run speed/current FOC with independent motor and controller models.

    New PI controllers are constructed for every run, avoiding state leakage
    between parameter experiments.
    """
    if dt <= 0 or simulation_time <= 0 or not 0 <= load_step_time < simulation_time:
        raise ValueError("Require dt > 0 and 0 <= load_step_time < simulation_time")
    if not np.isfinite(current_limit_a) or current_limit_a <= 0:
        raise ValueError("current_limit_a must be positive and finite")

    plant_params = plant_params if plant_params is not None else PMSMParameters()
    controller_params = controller_params if controller_params is not None else PMSMParameters()
    if commissioning_result is not None and commissioning_result.quality.accepted:
        controller_params = commissioning_result.retuned_controller_parameters(controller_params)
    motor = PMSMModel(plant_params)

    # Inner current-control loop
    current_controller = CurrentFOCController(
        controller_params,
        current_bandwidth_hz=300.0,
        dc_bus_voltage=dc_bus_voltage,
    )

    # Outer speed-control loop
    speed_controller = SpeedController(
        controller_params,
        natural_frequency_hz=10.0,
        damping_ratio=1.0,
        iq_limit=current_limit_a
    )

    time = np.arange(
        0.0,
        simulation_time,
        dt
    )

    # State:
    # [id, iq, omega_m, theta_e]
    state = np.zeros(4)

    # Desired motor speed
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
    voltage_d_history = np.zeros(len(time))
    voltage_q_history = np.zeros(len(time))
    voltage_magnitude_history = np.zeros(len(time))
    requested_voltage_magnitude_history = np.zeros(len(time))
    voltage_saturated_history = np.zeros(len(time), dtype=bool)

    for k, t in enumerate(time):

        i_d = state[0]
        i_q = state[1]
        omega_m = state[2]

        # Apply the configured load step.
        if t < load_step_time:
            load_torque = 0.0
        else:
            load_torque = load_step_torque

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
        voltage_d_history[k] = v_d
        voltage_q_history[k] = v_q
        voltage_magnitude_history[k] = current_controller.voltage_magnitude
        requested_voltage_magnitude_history[k] = current_controller.requested_voltage_magnitude
        voltage_saturated_history[k] = current_controller.voltage_saturated

    return {
        "time": time,
        "rpm": rpm_history,
        "id": id_history,
        "iq": iq_history,
        "iq_ref": iq_ref_history,
        "torque": torque_history,
        "load_torque": load_history,
        "voltage_d": voltage_d_history,
        "voltage_q": voltage_q_history,
        "voltage_magnitude": voltage_magnitude_history,
        "requested_voltage_magnitude": requested_voltage_magnitude_history,
        "voltage_saturated": voltage_saturated_history,
        "dc_bus_voltage": dc_bus_voltage,
        "voltage_limit": current_controller.voltage_limit,
        "current_limit_a": current_limit_a,
        "speed_ref_rpm": speed_ref_rpm,
        "load_step_time": load_step_time,
        "plant_params": plant_params,
        "controller_params": controller_params,
        "commissioning_accepted": (None if commissioning_result is None else
                                   commissioning_result.quality.accepted),
        "commissioning_rejection_reasons": (() if commissioning_result is None else
                                           commissioning_result.quality.rejection_reasons),
    }


def main():
    result = run_speed_foc_simulation()
    time = result["time"]
    rpm_history = result["rpm"]
    id_history = result["id"]
    iq_history = result["iq"]
    iq_ref_history = result["iq_ref"]
    torque_history = result["torque"]
    load_history = result["load_torque"]
    speed_ref_rpm = result["speed_ref_rpm"]

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
        result["load_step_time"],
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

    plt.figure()
    plt.plot(time, result["voltage_magnitude"], label="Applied dq voltage")
    if result["voltage_limit"] is not None:
        plt.axhline(result["voltage_limit"], linestyle="--", label="SVPWM limit")
    plt.xlabel("Time [s]")
    plt.ylabel("Voltage magnitude [V]")
    plt.title("Current-Controller Voltage Command")
    plt.grid()
    plt.legend()

    plt.show()


if __name__ == "__main__":
    main()
