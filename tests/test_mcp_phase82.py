from __future__ import annotations

import sys
import types

from phios.mcp.resources.dispatch_graph import read_dispatch_graph_last_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.dispatch_graph import phi_optimize_dispatch_graph


def _graph() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": ["a"]},
        ]
    }


def test_phase82_tool_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = phi_optimize_dispatch_graph(graph=_graph())
    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["read_only"] is True


def test_phase82_resource_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _ = phi_optimize_dispatch_graph(graph=_graph())
    out = read_dispatch_graph_last_resource()
    assert out["resource_version"] == "2.0"
    assert out["resource_kind"] == "dispatch_graph_last"


def test_phase82_server_registration(monkeypatch):
    class FakeFastMCP:
        def __init__(self, _name):
            self.resources = {}
            self.tools = {}
            self.prompts = {}

        def resource(self, uri, **_kwargs):
            def deco(fn):
                self.resources[uri] = fn
                return fn

            return deco

        def tool(self, name=None, **_kwargs):
            def deco(fn):
                self.tools[name or fn.__name__] = fn
                return fn

            return deco

        def prompt(self, name=None, **_kwargs):
            def deco(fn):
                self.prompts[name or fn.__name__] = fn
                return fn

            return deco

        def run(self, **_kwargs):
            return None

    fake_mod = types.ModuleType("mcp.server.fastmcp")
    fake_mod.FastMCP = FakeFastMCP
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fake_mod)

    server = create_mcp_server()
    reg = mcp_surface_registry()
    assert "phi_optimize_dispatch_graph" in server.tools
    assert "phios://dispatch/graph/last" in server.resources
    assert "phi_optimize_dispatch_graph" in reg.tools
    assert "phios://dispatch/graph/last" in reg.resources
