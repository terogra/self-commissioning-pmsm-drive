import numpy as np


def clarke_transform(a, b, c):
    """
    Three-phase abc quantities -> stationary alpha-beta frame.

    Amplitude-invariant Clarke transform.
    """

    alpha = (2.0 / 3.0) * (
        a
        - 0.5 * b
        - 0.5 * c
    )

    beta = (2.0 / 3.0) * (
        (np.sqrt(3.0) / 2.0) * (b - c)
    )

    return alpha, beta


def inverse_clarke_transform(alpha, beta):
    """
    Stationary alpha-beta frame -> three-phase abc quantities.
    """

    a = alpha

    b = (
        -0.5 * alpha
        + (np.sqrt(3.0) / 2.0) * beta
    )

    c = (
        -0.5 * alpha
        - (np.sqrt(3.0) / 2.0) * beta
    )

    return a, b, c


def park_transform(alpha, beta, theta_e):
    """
    Stationary alpha-beta frame -> rotating dq frame.
    """

    cos_theta = np.cos(theta_e)
    sin_theta = np.sin(theta_e)

    d = (
        alpha * cos_theta
        + beta * sin_theta
    )

    q = (
        -alpha * sin_theta
        + beta * cos_theta
    )

    return d, q


def inverse_park_transform(d, q, theta_e):
    """
    Rotating dq frame -> stationary alpha-beta frame.
    """

    cos_theta = np.cos(theta_e)
    sin_theta = np.sin(theta_e)

    alpha = (
        d * cos_theta
        - q * sin_theta
    )

    beta = (
        d * sin_theta
        + q * cos_theta
    )

    return alpha, beta