from __future__ import annotations

from math import sqrt

import pytest

from phios.core.constants import C_STAR_THEORETICAL, PHI
from phios.ml.golden_kernels import (
    golden_angular_rbf,
    golden_periodic,
    golden_rbf,
    golden_target_angle_score,
)


def _eigvals_3x3_sym(m):
    # Lightweight numeric sanity for PSD checks via principal minors.
    a, b, c = m[0]
    d, e = m[1][1], m[1][2]
    f = m[2][2]
    det1 = a
    det2 = a * d - b * b
    det3 = a * (d * f - e * e) - b * (b * f - c * e) + c * (b * e - c * d)
    return det1, det2, det3


def test_constants_formula_exactness():
    assert abs(PHI - ((1 + sqrt(5.0)) / 2.0)) < 1e-12
    assert abs(C_STAR_THEORETICAL - (PHI / 2.0)) < 1e-12


def test_golden_rbf_shape_symmetry_and_psd_sanity():
    X = [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]]
    K = golden_rbf(X, X)
    assert len(K) == 3 and len(K[0]) == 3
    assert K[0][1] == pytest.approx(K[1][0])
    assert K[1][2] == pytest.approx(K[2][1])
    d1, d2, d3 = _eigvals_3x3_sym(K)
    assert d1 >= -1e-9 and d2 >= -1e-9 and d3 >= -1e-9


def test_golden_angular_rbf_zero_vector_safety():
    X = [[0.0, 0.0], [1.0, 0.0]]
    K = golden_angular_rbf(X, X)
    assert len(K) == 2 and len(K[0]) == 2
    assert all(v == v for row in K for v in row)


def test_golden_periodic_basic_and_validation():
    t = [0.0, 0.2, 0.4]
    K = golden_periodic(t, t)
    assert len(K) == 3 and len(K[0]) == 3
    assert K[0][1] == pytest.approx(K[1][0])
    with pytest.raises(ValueError):
        golden_periodic(t, t, period=0.0)


def test_golden_target_angle_score_is_score_not_kernel():
    X = [[1.0, 0.0], [0.0, 1.0]]
    S = golden_target_angle_score(X, X)
    assert len(S) == 2 and len(S[0]) == 2
    assert all(0.0 <= v <= 1.0 for row in S for v in row)


def test_parameter_validation():
    X = [[1.0, 0.0]]
    with pytest.raises(ValueError):
        golden_rbf(X, X, length_scale=0.0)
    with pytest.raises(ValueError):
        golden_angular_rbf(X, X, tau=0.0)
    with pytest.raises(ValueError):
        golden_target_angle_score(X, X, eta=0.0)
