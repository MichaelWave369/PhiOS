"""Experimental 4D golden-lattice and adaptive-affinity utilities.

This module is optional/operator-side similarity tooling. It is not used for
PhiKernel source-of-truth runtime logic.
"""

from __future__ import annotations

from math import exp, sqrt
from typing import Sequence

from phios.core.constants import C_STAR_THEORETICAL

Matrix = list[list[float]]
Vector = list[float]
Node4 = tuple[int, int, int, int]


def build_lattice_4d_nodes(shape: tuple[int, int, int, int] = (12, 12, 12, 12)) -> list[Node4]:
    """Build integer-coordinate nodes for a 4D lattice."""
    if any(n <= 0 for n in shape):
        raise ValueError("shape dimensions must be positive")
    a, b, c, d = shape
    return [(i, j, k, m) for i in range(a) for j in range(b) for k in range(c) for m in range(d)]


def _l1(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return sqrt(sum(x * x for x in a))


def golden_lattice_kernel_l1(nodes_a: Sequence[Sequence[float]], nodes_b: Sequence[Sequence[float]], decay: float = C_STAR_THEORETICAL) -> Matrix:
    """Experimental geometric L1-decay similarity kernel core: decay ** L1."""
    if not (0.0 < decay < 1.0):
        raise ValueError("decay must be in (0, 1)")
    a = [list(map(float, n)) for n in nodes_a]
    b = [list(map(float, n)) for n in nodes_b]
    if not a or not b:
        raise ValueError("nodes_a and nodes_b must be non-empty")
    if len(a[0]) != len(b[0]):
        raise ValueError("node dimensions must match")
    return [[decay ** _l1(x, y) for y in b] for x in a]


def golden_lattice_sparse_graph(
    nodes: Sequence[Sequence[float]],
    max_l1_radius: int | None = None,
    max_neighbors: int | None = None,
) -> dict[str, object]:
    """Build sparse local neighborhoods for lattice-like coordinates."""
    pts = [list(map(float, n)) for n in nodes]
    if not pts:
        return {"node_count": 0, "edges": {}}
    radius = max_l1_radius if max_l1_radius is not None else 1
    if radius <= 0:
        raise ValueError("max_l1_radius must be > 0")
    if max_neighbors is not None and max_neighbors <= 0:
        raise ValueError("max_neighbors must be > 0")

    edges: dict[int, list[dict[str, float]]] = {}
    for i, src in enumerate(pts):
        local: list[tuple[int, float]] = []
        for j, dst in enumerate(pts):
            if i == j:
                continue
            dist = _l1(src, dst)
            if dist <= float(radius):
                local.append((j, dist))
        local.sort(key=lambda t: (t[1], t[0]))
        if max_neighbors is not None:
            local = local[:max_neighbors]
        edges[i] = [{"to": float(j), "l1": float(d)} for j, d in local]
    return {
        "node_count": len(pts),
        "max_l1_radius": radius,
        "max_neighbors": max_neighbors,
        "edges": edges,
    }


def golden_lattice_resonance_score(nodes_a: Sequence[Sequence[float]], nodes_b: Sequence[Sequence[float]], eta: float = 0.1, eps: float = 1e-12) -> Matrix:
    """Experimental resonance affinity score (not guaranteed PSD kernel)."""
    if eta <= 0:
        raise ValueError("eta must be > 0")
    if eps <= 0:
        raise ValueError("eps must be > 0")
    a = [list(map(float, n)) for n in nodes_a]
    b = [list(map(float, n)) for n in nodes_b]
    if not a or not b:
        raise ValueError("nodes_a and nodes_b must be non-empty")
    if len(a[0]) != len(b[0]):
        raise ValueError("node dimensions must match")

    a_norm = [[v / (_norm(x) + eps) for v in x] for x in a]
    b_norm = [[v / (_norm(y) + eps) for v in y] for y in b]
    denom = 2.0 * (eta**2)
    return [[exp(-((_dot(x, y) - C_STAR_THEORETICAL) ** 2) / denom) for y in b_norm] for x in a_norm]


def estimate_local_scales(X: Sequence[Sequence[float]], k: int = 5, eps: float = 1e-12) -> Vector:
    """Estimate per-point local scales from k-nearest Euclidean neighbors."""
    pts = [list(map(float, row)) for row in X]
    if not pts:
        return []
    if k <= 0:
        raise ValueError("k must be > 0")
    out: Vector = []
    for i, p in enumerate(pts):
        dists: list[float] = []
        for j, q in enumerate(pts):
            if i == j:
                continue
            d = sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))
            dists.append(d)
        if not dists:
            out.append(1.0)
            continue
        dists.sort()
        keep = dists[: min(k, len(dists))]
        out.append((sum(keep) / len(keep)) + eps)
    return out


def adaptive_golden_affinity(
    X: Sequence[Sequence[float]],
    Y: Sequence[Sequence[float]] | None = None,
    local_scales_x: Sequence[float] | None = None,
    local_scales_y: Sequence[float] | None = None,
    eps: float = 1e-12,
) -> Matrix:
    """Experimental memory-weighted affinity (not guaranteed PSD kernel)."""
    x = [list(map(float, row)) for row in X]
    y = x if Y is None else [list(map(float, row)) for row in Y]
    if not x or not y:
        raise ValueError("X and Y must be non-empty")
    if len(x[0]) != len(y[0]):
        raise ValueError("X and Y dimensions must match")

    sx = list(local_scales_x) if local_scales_x is not None else estimate_local_scales(x)
    sy = list(local_scales_y) if local_scales_y is not None else estimate_local_scales(y)
    if len(sx) != len(x) or len(sy) != len(y):
        raise ValueError("local scale lengths must match X and Y lengths")

    out: Matrix = []
    for i, xi in enumerate(x):
        row: list[float] = []
        for j, yj in enumerate(y):
            d2 = sum((a - b) ** 2 for a, b in zip(xi, yj))
            band = max((sx[i] * sy[j]) * C_STAR_THEORETICAL, eps)
            row.append(exp(-d2 / (2.0 * band)))
        out.append(row)
    return out


def update_memory_weights(current_weights: Sequence[float], usage_signal: Sequence[float], alpha: float = 0.1) -> Vector:
    """Exponential moving update for local memory weights."""
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("alpha must be in [0, 1]")
    w = [float(v) for v in current_weights]
    u = [float(v) for v in usage_signal]
    if len(w) != len(u):
        raise ValueError("current_weights and usage_signal must have same length")
    return [((1.0 - alpha) * wi) + (alpha * ui) for wi, ui in zip(w, u)]
