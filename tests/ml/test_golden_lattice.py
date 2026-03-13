from __future__ import annotations

import pytest

from phios.ml.golden_lattice import (
    adaptive_golden_affinity,
    build_lattice_4d_nodes,
    estimate_local_scales,
    golden_lattice_kernel_l1,
    golden_lattice_resonance_score,
    golden_lattice_sparse_graph,
    update_memory_weights,
)


def test_build_lattice_nodes_shape_count():
    nodes = build_lattice_4d_nodes((2, 2, 2, 2))
    assert len(nodes) == 16
    assert nodes[0] == (0, 0, 0, 0)


def test_lattice_kernel_shape_symmetry_finite():
    pts = [[0, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0]]
    k = golden_lattice_kernel_l1(pts, pts)
    assert len(k) == 3 and len(k[0]) == 3
    assert k[0][1] == pytest.approx(k[1][0])
    assert all(v == v for row in k for v in row)


def test_sparse_graph_behavior():
    pts = [[0, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]]
    g = golden_lattice_sparse_graph(pts, max_l1_radius=1, max_neighbors=1)
    assert g["node_count"] == 3
    assert len(g["edges"][0]) <= 1


def test_resonance_shape_finite():
    pts = [[0, 0, 0, 0], [1, 1, 0, 0]]
    r = golden_lattice_resonance_score(pts, pts)
    assert len(r) == 2 and len(r[0]) == 2
    assert all(v == v for row in r for v in row)


def test_adaptive_local_scale_and_affinity():
    x = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    scales = estimate_local_scales(x, k=2)
    assert len(scales) == 3
    a = adaptive_golden_affinity(x)
    assert len(a) == 3 and len(a[0]) == 3
    assert all(v == v for row in a for v in row)


def test_update_memory_weights():
    out = update_memory_weights([1.0, 0.0], [0.0, 1.0], alpha=0.2)
    assert out[0] == pytest.approx(0.8)
    assert out[1] == pytest.approx(0.2)
