from __future__ import annotations

import sys
import types

from phios.mcp.resources.agent_memory import (
    read_agent_memory_coherence_resource,
    read_agent_memory_topic_resource,
    read_recent_agent_deliberations_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.agent_memory import phi_store_deliberation


def _positions() -> list[dict[str, object]]:
    return [{"figure": "Architect", "claim": "scope first", "stance": "pro"}]


def test_phase77_store_deliberation_gated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state")
    denied = phi_store_deliberation(
        topic="x",
        positions=_positions(),
        outcome="ok",
        winning_figure="Architect",
        coherence_trace=[0.1],
        tags=["x"],
    )
    assert denied["error_code"] == "AGENT_MEMORY_WRITE_NOT_PERMITTED"


def test_phase77_store_and_resources(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "agent_memory_write")
    out = phi_store_deliberation(
        topic="planning",
        positions=_positions(),
        outcome="consensus",
        winning_figure="Architect",
        coherence_trace=[0.4, 0.6],
        tags=["plan"],
    )
    assert out["ok"] is True
    topic = read_agent_memory_topic_resource("planning")
    coh = read_agent_memory_coherence_resource("planning")
    recent = read_recent_agent_deliberations_resource(10)
    assert topic["resource_kind"] == "agent_memory_topic"
    assert coh["resource_kind"] == "agent_memory_coherence"
    assert recent["resource_kind"] == "agent_deliberations_recent"


def test_phase77_server_registers_surfaces(monkeypatch):
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

    assert "phios://agents/memory/{topic}" in server.resources
    assert "phios://agents/memory/{topic}/coherence" in server.resources
    assert "phios://agents/deliberations/recent" in server.resources
    assert "phi_store_deliberation" in server.tools
    assert "phios://agents/memory/{topic}" in reg.resources
    assert "phi_store_deliberation" in reg.tools
