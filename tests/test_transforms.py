import numpy as np

from src.transforms import (
    clarke_transform,
    inverse_clarke_transform,
    park_transform,
    inverse_park_transform
)


def test_clarke_round_trip():
    a = 2.0
    b = -1.0
    c = -1.0

    alpha, beta = clarke_transform(
        a, b, c
    )

    a_back, b_back, c_back = (
        inverse_clarke_transform(
            alpha,
            beta
        )
    )

    assert np.isclose(a, a_back)
    assert np.isclose(b, b_back)
    assert np.isclose(c, c_back)


def test_park_round_trip():
    alpha = 1.4
    beta = -0.8
    theta_e = 1.2

    d, q = park_transform(
        alpha,
        beta,
        theta_e
    )

    alpha_back, beta_back = (
        inverse_park_transform(
            d,
            q,
            theta_e
        )
    )

    assert np.isclose(
        alpha,
        alpha_back
    )

    assert np.isclose(
        beta,
        beta_back
    )