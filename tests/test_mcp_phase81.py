from __future__ import annotations

import sys
import types

from phios.mcp.resources.cognitive_atoms import read_cognition_atoms_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.cognitive_atoms import run_phi_recommend_cognitive_atoms


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.79,
            "distance_to_C_star": 0.02,
            "geometry_balance": 0.7,
            "vacuum_proximity": 0.8,
            "observer_entropy": 0.75,
            "collector_activity": 0.65,
            "mirror_alignment": 0.7,
            "emotion_field": 0.68,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def test_phase81_tool_shape():
    out = run_phi_recommend_cognitive_atoms(DummyAdapter())
    assert out["ok"] is True
    assert out["read_only"] is True
    assert out["tool_version"] == "2.0"
    assert "atom_overrides" in out["recommendation"]


def test_phase81_resource_shape():
    out = read_cognition_atoms_resource(DummyAdapter())
    assert out["resource_version"] == "2.0"
    assert out["resource_kind"] == "cognitive_atom_recommendation"
    assert out["read_only"] is True


def test_phase81_server_registration(monkeypatch):
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

    server = create_mcp_server(adapter=DummyAdapter())
    reg = mcp_surface_registry()

    assert "phi_recommend_cognitive_atoms" in server.tools
    assert "phios://cognition/atoms" in server.resources
    assert "phi_recommend_cognitive_atoms" in reg.tools
    assert "phios://cognition/atoms" in reg.resources
