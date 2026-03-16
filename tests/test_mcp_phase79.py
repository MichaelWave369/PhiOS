from __future__ import annotations

import sys
import types

from phios.mcp.resources.agents import (
    read_agent_run_events_resource,
    read_agent_run_resource,
    read_agents_active_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.agents import (
    run_phi_agent_status,
    run_phi_dispatch_agents,
    run_phi_kill_agent,
    run_phi_list_agents,
)


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.4,
            "C_star": 0.93,
            "recommended_action": "stabilize",
            "field_band": "amber",
        }

    def capsule_list(self):
        return {"capsules": [1]}


def test_phase79_dispatch_dry_run_and_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state,read_history,read_observatory")

    denied = run_phi_dispatch_agents(DummyAdapter(), task="x", dry_run=False)
    assert denied["error_code"] == "AGENT_DISPATCH_NOT_PERMITTED"

    dry = run_phi_dispatch_agents(DummyAdapter(), task="x", dry_run=True, field_guided=True)
    assert dry["ok"] is True
    assert dry["dry_run"] is True
    assert "field_state" in dry["context"]

    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "agent_dispatch")
    gated = run_phi_dispatch_agents(
        DummyAdapter(),
        task="x",
        dry_run=True,
        field_guided=True,
        coherence_gate=0.8,
    )
    assert gated["error_code"] == "COHERENCE_GATE_BLOCKED"


def test_phase79_list_status_kill_and_resources(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "agent_dispatch,agent_kill")

    out = run_phi_dispatch_agents(DummyAdapter(), task="run", dry_run=False)
    run_id = str(out["run"]["run_id"])

    listed = run_phi_list_agents()
    assert listed["count"] >= 1

    status = run_phi_agent_status(run_id=run_id)
    assert status["ok"] is True

    kill = run_phi_kill_agent(run_id=run_id)
    assert kill["ok"] is True

    active = read_agents_active_resource()
    one = read_agent_run_resource(run_id)
    events = read_agent_run_events_resource(run_id)
    assert active["resource_kind"] == "agents_active"
    assert one["resource_kind"] == "agent_run"
    assert events["resource_kind"] == "agent_run_events"


def test_phase79_server_registers_surfaces(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

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

    assert "phios://agents/active" in server.resources
    assert "phios://agents/{run_id}" in server.resources
    assert "phios://agents/{run_id}/events" in server.resources
    assert "phi_dispatch_agents" in server.tools
    assert "phi_list_agents" in server.tools
    assert "phi_agent_status" in server.tools
    assert "phi_kill_agent" in server.tools
    assert "phios://agents/active" in reg.resources
    assert "phi_dispatch_agents" in reg.tools
