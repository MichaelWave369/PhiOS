from __future__ import annotations

from phios.services.dispatch_graph import optimize_dispatch_graph


def test_valid_dag_order_and_waves(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    graph = {
        "nodes": [
            {"id": "a", "dependencies": [], "estimated_cost": 2.0},
            {"id": "b", "dependencies": ["a"], "estimated_cost": 1.0},
            {"id": "c", "dependencies": ["a"], "estimated_cost": 1.0},
            {"id": "d", "dependencies": ["b", "c"], "estimated_cost": 2.0},
        ]
    }
    out = optimize_dispatch_graph(graph)
    assert out["ok"] is True
    assert out["ordered_nodes"][0] == "a"
    assert out["dispatch_waves"][0] == ["a"]
    assert set(out["dispatch_waves"][1]) == {"b", "c"}


def test_dependency_violation_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    graph = {"nodes": [{"id": "a", "dependencies": ["missing"]}]}
    out = optimize_dispatch_graph(graph)
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_GRAPH"


def test_deterministic_ordering(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    graph = {
        "nodes": [
            {"id": "x", "dependencies": [], "priority": 1, "estimated_cost": 1.0},
            {"id": "y", "dependencies": [], "priority": 1, "estimated_cost": 1.0},
        ]
    }
    out1 = optimize_dispatch_graph(graph)
    out2 = optimize_dispatch_graph(graph)
    assert out1["ordered_nodes"] == out2["ordered_nodes"]


def test_bottleneck_detection(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    graph = {
        "nodes": [
            {"id": "root", "dependencies": []},
            {"id": "n1", "dependencies": ["root"]},
            {"id": "n2", "dependencies": ["root"]},
            {"id": "n3", "dependencies": ["root"]},
        ]
    }
    out = optimize_dispatch_graph(graph)
    assert "root" in out["bottlenecks"]
