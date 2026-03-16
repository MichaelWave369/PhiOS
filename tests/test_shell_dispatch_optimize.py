from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_dispatch_optimize_json(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    graph = json.dumps(
        {
            "nodes": [
                {"id": "a", "dependencies": []},
                {"id": "b", "dependencies": ["a"]},
            ]
        }
    )
    out, code = route_command(["dispatch", "optimize", "--graph", graph, "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert "ordered_nodes" in payload["plan"]
