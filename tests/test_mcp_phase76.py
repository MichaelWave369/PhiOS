from __future__ import annotations

import sys
import types

from phios.mcp.resources.cognitive_arch import read_cognition_recommendation_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.cognitive_arch import run_phi_recommend_cognitive_arch


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.81,
            "distance_to_C_star": 0.0,
            "recommended_action": "maintain",
            "field_band": "green",
            "fragmentation_score": 0.12,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def test_phase76_tool_shape_and_schema(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = run_phi_recommend_cognitive_arch(DummyAdapter())
    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["read_only"] is True
    rec = out["recommendation"]
    assert "figure" in rec
    assert "archetype" in rec
    assert "reason" in rec
    assert "confidence" in rec
    assert rec["experimental"] is True


def test_phase76_resource_shape(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = read_cognition_recommendation_resource(DummyAdapter())
    assert out["resource_version"] == "2.0"
    assert out["read_only"] is True
    assert out["resource_kind"] == "cognitive_arch_recommendation"
    assert "recommendation" in out


def test_phase76_server_registers_surfaces(monkeypatch):
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

    assert "phi_recommend_cognitive_arch" in server.tools
    assert "phios://cognition/recommendation" in server.resources
    assert "phi_recommend_cognitive_arch" in reg.tools
    assert "phios://cognition/recommendation" in reg.resources


def test_phase76_sparse_fallback(monkeypatch):
    class SparseAdapter:
        def status(self):
            return {}

        def field(self):
            return {}

        def capsule_list(self):
            return {}

    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = run_phi_recommend_cognitive_arch(SparseAdapter())
    assert out["ok"] is True
    assert "recommendation" in out
