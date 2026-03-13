"""Experimental golden-prior kernels for local similarity tooling.

These functions are optional similarity primitives and inductive priors.
They do not alter source-of-truth runtime logic.
"""

from __future__ import annotations

from math import exp, pi, sin, sqrt
from typing import Sequence

from phios.core.constants import C_STAR_THEORETICAL


Matrix = list[list[float]]


def _to_matrix(data: Sequence[Sequence[float]], *, name: str) -> Matrix:
    rows: Matrix = [[float(v) for v in row] for row in data]
    if not rows:
        raise ValueError(f"{name} must have at least one row")
    width = len(rows[0])
    if width == 0:
        raise ValueError(f"{name} must have non-empty rows")
    if any(len(r) != width for r in rows):
        raise ValueError(f"{name} rows must have equal width")
    return rows


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sqdist(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return sqrt(sum(x * x for x in a))


def golden_rbf(X: Sequence[Sequence[float]], Y: Sequence[Sequence[float]], length_scale: float = 1.0) -> Matrix:
    """RBF kernel with C* as an experimental scale prior."""
    if length_scale <= 0:
        raise ValueError("length_scale must be > 0")
    X2 = _to_matrix(X, name="X")
    Y2 = _to_matrix(Y, name="Y")
    if len(X2[0]) != len(Y2[0]):
        raise ValueError("X and Y must share feature dimension")
    denom = 2.0 * (length_scale**2) * C_STAR_THEORETICAL
    return [[exp(-_sqdist(x, y) / denom) for y in Y2] for x in X2]


def golden_angular_rbf(
    X: Sequence[Sequence[float]],
    Y: Sequence[Sequence[float]],
    tau: float = 1.0,
    eps: float = 1e-12,
) -> Matrix:
    """RBF-like kernel over normalized vectors (angular geometry)."""
    if tau <= 0:
        raise ValueError("tau must be > 0")
    if eps <= 0:
        raise ValueError("eps must be > 0")
    X2 = _to_matrix(X, name="X")
    Y2 = _to_matrix(Y, name="Y")
    if len(X2[0]) != len(Y2[0]):
        raise ValueError("X and Y must share feature dimension")

    Xn = [[v / (_norm(x) + eps) for v in x] for x in X2]
    Yn = [[v / (_norm(y) + eps) for v in y] for y in Y2]
    denom = 2.0 * (tau**2) * C_STAR_THEORETICAL
    return [[exp(-_sqdist(x, y) / denom) for y in Yn] for x in Xn]


def golden_periodic(
    tX: Sequence[float],
    tY: Sequence[float],
    period: float = C_STAR_THEORETICAL,
    length_scale: float = 1.0,
) -> Matrix:
    """PSD periodic kernel with optional C*-prior period."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if length_scale <= 0:
        raise ValueError("length_scale must be > 0")
    x = [float(v) for v in tX]
    y = [float(v) for v in tY]
    if not x or not y:
        raise ValueError("tX and tY must be non-empty")
    return [[exp(-2.0 * sin(pi * abs(a - b) / period) ** 2 / (length_scale**2)) for b in y] for a in x]


def golden_target_angle_score(
    X: Sequence[Sequence[float]],
    Y: Sequence[Sequence[float]],
    eta: float = 0.1,
    eps: float = 1e-12,
) -> Matrix:
    """Affinity score favoring cosine similarity near theoretical C*.

    Note: this is a score function, not automatically guaranteed PSD.
    """
    if eta <= 0:
        raise ValueError("eta must be > 0")
    if eps <= 0:
        raise ValueError("eps must be > 0")
    X2 = _to_matrix(X, name="X")
    Y2 = _to_matrix(Y, name="Y")
    if len(X2[0]) != len(Y2[0]):
        raise ValueError("X and Y must share feature dimension")
    Xn = [[v / (_norm(x) + eps) for v in x] for x in X2]
    Yn = [[v / (_norm(y) + eps) for v in y] for y in Y2]
    denom = 2.0 * (eta**2)
    return [[exp(-((_dot(x, y) - C_STAR_THEORETICAL) ** 2) / denom) for y in Yn] for x in Xn]
