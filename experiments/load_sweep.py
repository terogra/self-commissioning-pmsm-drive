from pathlib import Path
import csv

import matplotlib.pyplot as plt
import numpy as np

from src.simulation import (
    run_open_loop_simulation,
    steady_state_mean
)


LOAD_TORQUES = [
    0.00,
    0.05,
    0.10
]


def main():

    results = []

    for load_torque in LOAD_TORQUES:

        simulation = run_open_loop_simulation(
            load_torque=load_torque
        )

        params = simulation["params"]

        id_ss = steady_state_mean(
            simulation["id"]
        )

        iq_ss = steady_state_mean(
            simulation["iq"]
        )

        rpm_ss = steady_state_mean(
            simulation["rpm"]
        )

        torque_ss = steady_state_mean(
            simulation["torque"]
        )

        omega_ss = (
            rpm_ss
            * 2.0
            * np.pi
            / 60.0
        )

        # Mechanical steady-state balance:
        # Te = TL + B * omega
        expected_torque = (
            load_torque
            + params.B * omega_ss
        )

        balance_error = abs(
            torque_ss
            - expected_torque
        )

        results.append({
            "load_torque": load_torque,
            "id_ss": id_ss,
            "iq_ss": iq_ss,
            "rpm_ss": rpm_ss,
            "torque_ss": torque_ss,
            "expected_torque": expected_torque,
            "balance_error": balance_error
        })

    # -----------------------------
    # Print result table
    # -----------------------------

    print()
    print(
        "Load [Nm] | "
        "id [A] | "
        "iq [A] | "
        "Speed [rpm] | "
        "Te [Nm] | "
        "Balance Error"
    )

    print("-" * 85)

    for row in results:

        print(
            f"{row['load_torque']:8.3f} | "
            f"{row['id_ss']:6.4f} | "
            f"{row['iq_ss']:6.4f} | "
            f"{row['rpm_ss']:11.2f} | "
            f"{row['torque_ss']:7.4f} | "
            f"{row['balance_error']:.6f}"
        )

    # -----------------------------
    # Automatic validation
    # -----------------------------

    speeds = [
        row["rpm_ss"]
        for row in results
    ]

    iq_values = [
        row["iq_ss"]
        for row in results
    ]

    assert (
        speeds[0]
        > speeds[1]
        > speeds[2]
    ), "Speed should decrease as load increases."

    assert (
        iq_values[0]
        < iq_values[1]
        < iq_values[2]
    ), "iq should increase as load increases."

    for row in results:

        assert (
            row["balance_error"]
            < 1e-3
        ), (
            "Mechanical steady-state "
            "torque balance failed."
        )

    print()
    print(
        "PASS: "
        "Open-loop load-sweep validation successful."
    )

    # -----------------------------
    # Save CSV
    # -----------------------------

    results_directory = Path("results")
    results_directory.mkdir(
        exist_ok=True
    )

    csv_path = (
        results_directory
        / "open_loop_load_sweep.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=results[0].keys()
        )

        writer.writeheader()
        writer.writerows(results)

    # -----------------------------
    # Plot
    # -----------------------------

    loads = [
        row["load_torque"]
        for row in results
    ]

    plt.figure()

    plt.plot(
        loads,
        speeds,
        marker="o"
    )

    plt.xlabel(
        "Load Torque [N.m]"
    )

    plt.ylabel(
        "Steady-State Speed [rpm]"
    )

    plt.title(
        "Open-Loop PMSM Load Sweep"
    )

    plt.grid()

    figure_path = (
        results_directory
        / "open_loop_load_sweep.png"
    )

    plt.savefig(
        figure_path,
        dpi=200,
        bbox_inches="tight"
    )

    plt.show()


if __name__ == "__main__":
    main()