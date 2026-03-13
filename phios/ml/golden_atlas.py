"""Experimental Golden Atlas local navigation utilities.

This module is optional and experimental. It does not alter PhiKernel truth logic.
Similarity/coupling and traversal cost are intentionally separated.
"""

from __future__ import annotations

from heapq import heappop, heappush
from itertools import product
from math import sqrt
from typing import Sequence

from phios.ml.golden_lattice import build_lattice_4d_nodes as _build_lattice_4d_nodes

from phios.core.constants import (
    BIO_VACUUM_BAND_HIGH,
    BIO_VACUUM_BAND_LOW,
    BIO_VACUUM_TARGET,
    C_STAR_THEORETICAL,
)

Vector = list[float]


def build_lattice_4d_nodes(shape: tuple[int, int, int, int] = (12, 12, 12, 12)) -> list[tuple[int, int, int, int]]:
    """Forward-compatible lattice node builder for atlas use."""
    return _build_lattice_4d_nodes(shape)


def _as_points(nodes: Sequence[Sequence[float]]) -> list[Vector]:
    pts = [list(map(float, n)) for n in nodes]
    if not pts:
        raise ValueError("nodes must be non-empty")
    width = len(pts[0])
    if width == 0 or any(len(p) != width for p in pts):
        raise ValueError("nodes must have a stable non-empty dimension")
    return pts


def _l1(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b))


def _l2(a: Sequence[float], b: Sequence[float]) -> float:
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def nearest_lattice_node(nodes: Sequence[Sequence[float]], point: Sequence[float]) -> int:
    pts = _as_points(nodes)
    q = list(map(float, point))
    if len(q) != len(pts[0]):
        raise ValueError("point dimension must match node dimension")
    best_idx = 0
    best = _l2(pts[0], q)
    for i, p in enumerate(pts[1:], start=1):
        d = _l2(p, q)
        if d < best:
            best = d
            best_idx = i
    return best_idx


def build_golden_atlas_graph(
    nodes: Sequence[Sequence[float]],
    max_l1_radius: int = 1,
    max_neighbors: int | None = None,
) -> dict[str, object]:
    pts = _as_points(nodes)
    if max_l1_radius <= 0:
        raise ValueError("max_l1_radius must be > 0")
    if max_neighbors is not None and max_neighbors <= 0:
        raise ValueError("max_neighbors must be > 0")

    # Sparse default: resolve neighborhood via coordinate lookup (no dense all-pairs).
    int_like = all(all(abs(v - round(v)) < 1e-9 for v in p) for p in pts)
    edges: dict[int, list[dict[str, float]]] = {}

    if int_like:
        coord_to_idx = {tuple(int(round(v)) for v in p): i for i, p in enumerate(pts)}
        dim = len(pts[0])
        offsets = [
            off
            for off in product(range(-max_l1_radius, max_l1_radius + 1), repeat=dim)
            if 0 < sum(abs(x) for x in off) <= max_l1_radius
        ]
        for i, p in enumerate(pts):
            base = tuple(int(round(v)) for v in p)
            local_int: list[tuple[int, float]] = []
            for off in offsets:
                q = tuple(base[d] + off[d] for d in range(dim))
                j = coord_to_idx.get(q)
                if j is None or j == i:
                    continue
                d = float(sum(abs(x) for x in off))
                local_int.append((j, d))
            local_int.sort(key=lambda t: (t[1], t[0]))
            if max_neighbors is not None:
                local_int = local_int[:max_neighbors]
            edges[i] = [{"to": float(j), "l1": d, "coupling": C_STAR_THEORETICAL**d} for j, d in local_int]
    else:
        # fallback for non-integer points (still sparse via radius and optional neighbor cap)
        for i, src in enumerate(pts):
            local: list[tuple[int, float]] = []
            for j, dst in enumerate(pts):
                if i == j:
                    continue
                d = _l1(src, dst)
                if d <= float(max_l1_radius):
                    local.append((j, d))
            local.sort(key=lambda t: (t[1], t[0]))
            if max_neighbors is not None:
                local = local[:max_neighbors]
            edges[i] = [{"to": float(j), "l1": float(d), "coupling": C_STAR_THEORETICAL**d} for j, d in local]

    return {
        "node_count": len(pts),
        "max_l1_radius": max_l1_radius,
        "max_neighbors": max_neighbors,
        "edges": edges,
        "experimental": True,
    }


def compute_golden_travel_cost(
    node_a: Sequence[float],
    node_b: Sequence[float],
    *,
    alpha: float = 1.0,
    beta: float = 0.0,
    gamma: float = 0.0,
    target_point: Sequence[float] | None = None,
) -> float:
    """Monotone-in-distance travel cost for routing (not similarity)."""
    if alpha <= 0:
        raise ValueError("alpha must be > 0")
    a = list(map(float, node_a))
    b = list(map(float, node_b))
    if len(a) != len(b):
        raise ValueError("node dimensions must match")

    base = alpha * _l1(a, b)
    if target_point is None:
        return base

    t = list(map(float, target_point))
    if len(t) != len(a):
        raise ValueError("target_point dimension must match node dimension")
    # optional penalties remain additive over monotone base
    target_penalty = beta * _l2(b, t)
    smooth_penalty = gamma * abs(_l2(a, t) - _l2(b, t))
    return base + target_penalty + smooth_penalty


def _dijkstra(
    pts: list[Vector],
    graph: dict[str, object],
    start_idx: int,
    goal_check,
    target_point: Sequence[float] | None = None,
) -> dict[str, object]:
    edges_obj = graph.get("edges")
    edges = edges_obj if isinstance(edges_obj, dict) else {}
    n = len(pts)
    if start_idx < 0 or start_idx >= n:
        raise ValueError("start_idx out of bounds")

    dist = [float("inf")] * n
    prev: list[int | None] = [None] * n
    dist[start_idx] = 0.0
    pq: list[tuple[float, int]] = [(0.0, start_idx)]
    found: int | None = None

    while pq:
        d, u = heappop(pq)
        if d > dist[u]:
            continue
        if goal_check(u):
            found = u
            break
        neighbors_obj = edges.get(u, [])
        neighbors = neighbors_obj if isinstance(neighbors_obj, list) else []
        for row in neighbors:
            if not isinstance(row, dict):
                continue
            v = int(float(row.get("to", -1)))
            if v < 0 or v >= n:
                continue
            w = compute_golden_travel_cost(pts[u], pts[v], target_point=target_point)
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heappush(pq, (nd, v))

    if found is None:
        return {"reachable": False, "path": [], "cost": float("inf"), "end_idx": None}

    path = []
    cur: int | None = found
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return {"reachable": True, "path": path, "cost": dist[found], "end_idx": found}


def find_path_to_target(
    nodes: Sequence[Sequence[float]],
    graph: dict[str, object],
    start_idx: int,
    target_idx: int,
    *,
    target_point: Sequence[float] | None = None,
) -> dict[str, object]:
    pts = _as_points(nodes)
    if target_idx < 0 or target_idx >= len(pts):
        raise ValueError("target_idx out of bounds")
    out = _dijkstra(pts, graph, start_idx, lambda i: i == target_idx, target_point=target_point)
    out["target_idx"] = target_idx
    out["target_mode"] = "explicit_target"
    return out


def find_path_to_bio_band(
    nodes: Sequence[Sequence[float]],
    graph: dict[str, object],
    start_idx: int,
    *,
    bio_target: float = BIO_VACUUM_TARGET,
    band_low: float = BIO_VACUUM_BAND_LOW,
    band_high: float = BIO_VACUUM_BAND_HIGH,
) -> dict[str, object]:
    pts = _as_points(nodes)

    def _in_band(i: int) -> bool:
        v = pts[i][0]
        return band_low <= v <= band_high

    out = _dijkstra(pts, graph, start_idx, _in_band, target_point=[bio_target] * len(pts[0]))
    out["target_mode"] = "bio_band"
    out["bio_target"] = bio_target
    out["band_low"] = band_low
    out["band_high"] = band_high
    return out


def compute_atlas_heat(
    nodes: Sequence[Sequence[float]],
    graph: dict[str, object],
    *,
    target_point: Sequence[float] | None = None,
    mode: str = "target_proximity",
) -> list[float]:
    pts = _as_points(nodes)
    m = mode.strip().lower()
    if m == "connectivity":
        edges_obj = graph.get("edges")
        edges = edges_obj if isinstance(edges_obj, dict) else {}
        return [float(len(edges.get(i, []))) for i in range(len(pts))]

    if m == "bio_band_proximity":
        target = [BIO_VACUUM_TARGET] * len(pts[0])
    else:
        target = list(map(float, target_point)) if target_point is not None else [C_STAR_THEORETICAL] * len(pts[0])

    if len(target) != len(pts[0]):
        raise ValueError("target_point dimension must match node dimension")

    vals = [1.0 / (1.0 + _l2(p, target)) for p in pts]
    if m == "path_density":
        # lightweight proxy: blend local connectivity with target proximity
        conn = compute_atlas_heat(pts, graph, mode="connectivity")
        return [0.5 * v + 0.5 * (c / (1.0 + c)) for v, c in zip(vals, conn)]
    return vals


def build_golden_atlas_summary(
    *,
    nodes: Sequence[Sequence[float]],
    graph: dict[str, object],
    path_result: dict[str, object],
    heat: Sequence[float],
    target_mode: str,
) -> dict[str, object]:
    vals = [float(v) for v in heat]
    edges_obj = graph.get("edges")
    edge_count = 0
    if isinstance(edges_obj, dict):
        edge_count = sum(len(v) for v in edges_obj.values() if isinstance(v, list))
    return {
        "experimental": True,
        "target_mode": target_mode,
        "node_count": len(_as_points(nodes)),
        "edge_count": edge_count,
        "path": path_result,
        "heat_min": min(vals) if vals else 0.0,
        "heat_max": max(vals) if vals else 0.0,
        "heat_avg": (sum(vals) / len(vals)) if vals else 0.0,
    }
