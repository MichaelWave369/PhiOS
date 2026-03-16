from __future__ import annotations

import sys
import types

from phios.mcp.resources.debates import read_debate_session_resource, read_debates_recent_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.debate import phi_debate_coherence_gate


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.65,
            "distance_to_C_star": 0.25,
            "recommended_action": "stabilize",
            "field_band": "amber",
            "fragmentation_score": 0.21,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def _positions() -> list[dict[str, object]]:
    return [{"figure": "Architect", "claim": "scope", "stance": "pro", "support": 0.8}]


def test_phase75_tool_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = phi_debate_coherence_gate(
        DummyAdapter(),
        session_id="sess-a",
        round=1,
        positions=_positions(),
        threshold=0.9,
        persist=False,
    )
    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["result"]["action"] in {"continue", "converged", "deadlock"}


def test_phase75_persist_and_resources(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _ = phi_debate_coherence_gate(
        DummyAdapter(),
        session_id="sess-b",
        round=2,
        positions=_positions(),
        threshold=0.9,
        persist=True,
    )
    recent = read_debates_recent_resource(10)
    one = read_debate_session_resource("sess-b")
    assert recent["resource_kind"] == "debates_recent"
    assert one["resource_kind"] == "debate_session"


def test_phase75_server_registration(monkeypatch):
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

    assert "phi_debate_coherence_gate" in server.tools
    assert "phios://debates/recent" in server.resources
    assert "phios://debates/{session_id}" in server.resources
    assert "phi_debate_coherence_gate" in reg.tools
    assert "phios://debates/recent" in reg.resources
