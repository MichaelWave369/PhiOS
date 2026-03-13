from __future__ import annotations

from phios.ml.golden_atlas import (
    build_golden_atlas_graph,
    build_golden_atlas_summary,
    build_lattice_4d_nodes,
    compute_atlas_heat,
    compute_golden_travel_cost,
    find_path_to_bio_band,
    find_path_to_target,
    nearest_lattice_node,
)


def test_nearest_node_resolution():
    nodes = [[0, 0, 0, 0], [1, 1, 1, 1], [2, 2, 2, 2]]
    assert nearest_lattice_node(nodes, [1.1, 1.0, 1.0, 1.0]) == 1


def test_graph_construction_and_pathfinding():
    nodes = [[0, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]]
    graph = build_golden_atlas_graph(nodes, max_l1_radius=1)
    out = find_path_to_target(nodes, graph, start_idx=0, target_idx=2, target_point=[2, 0, 0, 0])
    assert out["reachable"] is True
    assert out["path"] == [0, 1, 2]


def test_monotone_travel_cost():
    c1 = compute_golden_travel_cost([0, 0, 0, 0], [1, 0, 0, 0])
    c2 = compute_golden_travel_cost([0, 0, 0, 0], [2, 0, 0, 0])
    assert c2 > c1


def test_unreachable_graph_behavior():
    nodes = [[0, 0, 0, 0], [4, 0, 0, 0]]
    graph = build_golden_atlas_graph(nodes, max_l1_radius=1)
    out = find_path_to_target(nodes, graph, start_idx=0, target_idx=1)
    assert out["reachable"] is False


def test_bio_band_target_resolution_and_heat():
    nodes = [[0.79, 0, 0, 0], [0.809, 0, 0, 0], [0.82, 0, 0, 0]]
    graph = build_golden_atlas_graph(nodes, max_l1_radius=1)
    out = find_path_to_bio_band(nodes, graph, start_idx=0)
    assert out["target_mode"] == "bio_band"
    heat = compute_atlas_heat(nodes, graph, mode="bio_band_proximity")
    assert len(heat) == len(nodes)


def test_atlas_summary_schema():
    nodes = build_lattice_4d_nodes((2, 1, 1, 1))
    graph = build_golden_atlas_graph(nodes, max_l1_radius=1)
    path = find_path_to_target(nodes, graph, start_idx=0, target_idx=1)
    heat = compute_atlas_heat(nodes, graph)
    summary = build_golden_atlas_summary(nodes=nodes, graph=graph, path_result=path, heat=heat, target_mode="theoretical")
    assert summary["experimental"] is True
