import numpy as np

from src.motor import PMSMModel, PMSMParameters


def test_spmsm_torque_equation():
    """
    For an SPMSM where Ld = Lq, reluctance torque should vanish.
    Torque should therefore depend only on iq.
    """

    params = PMSMParameters()
    motor = PMSMModel(params)

    i_d = 0.0
    i_q = 2.0

    torque = motor.electromagnetic_torque(i_d, i_q)

    expected_torque = (
        1.5
        * params.pole_pairs
        * params.psi_f
        * i_q
    )

    assert np.isclose(
        torque,
        expected_torque
    )


def test_initial_q_axis_current_derivative():
    """
    At standstill, back-EMF is zero.

    Therefore, with iq = 0:
        diq/dt = vq / Lq
    """

    params = PMSMParameters()
    motor = PMSMModel(params)

    state = np.array([
        0.0,  # id
        0.0,  # iq
        0.0,  # mechanical speed
        0.0   # electrical angle
    ])

    v_d = 0.0
    v_q = 8.0
    load_torque = 0.0

    derivatives = motor.derivatives(
        state,
        v_d,
        v_q,
        load_torque
    )

    expected_diq = v_q / params.Lq

    assert np.isclose(
        derivatives[1],
        expected_diq
    )


def test_load_torque_causes_deceleration_without_motor_torque():
    """
    With zero electromagnetic torque and a positive load torque,
    the rotor must accelerate in the negative direction.
    """

    params = PMSMParameters()
    motor = PMSMModel(params)

    state = np.array([
        0.0,
        0.0,
        0.0,
        0.0
    ])

    load_torque = 0.05

    derivatives = motor.derivatives(
        state,
        v_d=0.0,
        v_q=0.0,
        load_torque=load_torque
    )

    expected_acceleration = (
        -load_torque / params.J
    )

    assert np.isclose(
        derivatives[2],
        expected_acceleration
    )