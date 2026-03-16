from __future__ import annotations

import os
import sys
import types

from phios.mcp.prompts.field_guidance import build_field_guidance_prompt
from phios.mcp.resources.coherence_lt import read_coherence_lt_resource
from phios.mcp.resources.field_state import read_field_state_resource
from phios.mcp.resources.history import (
    read_recent_capsules_resource,
    read_recent_field_snapshots_resource,
    read_recent_sessions_resource,
)
from phios.mcp.resources.status import read_system_status_resource
from phios.mcp.server import create_mcp_server, phase1_registry
from phios.mcp.tools.ask import run_phi_ask
from phios.mcp.tools.pulse import run_phi_pulse_once
from phios.mcp.tools.status import run_phi_status


class DummyAdapter:
    def capsule_list(self):
        return {"capsules": [{"id": "c1"}, {"id": "c2"}]}


def test_schema_versions_present_on_resources(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr("phios.mcp.resources.field_state.build_coherence_report", lambda _a: {"C_current": 0.7})
    monkeypatch.setattr("phios.mcp.resources.status.build_status_report", lambda _a: {"heart_state": "running"})
    monkeypatch.setattr("phios.mcp.resources.coherence_lt.compute_lt", lambda: {"lt": 0.8, "system_lt": 0.8, "components": {}, "phb_contribution": 0.0})

    for payload in (
        read_field_state_resource(adapter),
        read_system_status_resource(adapter),
        read_coherence_lt_resource(),
    ):
        assert "schema_version" in payload


def test_schema_versions_present_on_tools(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr("phios.mcp.tools.status.build_status_report", lambda _a: {"ok": True})
    monkeypatch.setattr("phios.mcp.tools.status.build_coherence_report", lambda _a: {"C_current": 0.5})
    monkeypatch.setattr("phios.mcp.tools.status.compute_lt", lambda: {"lt": 0.6})
    monkeypatch.setattr("phios.mcp.tools.ask.build_ask_report", lambda _a, _p: {"coach": "SovereignCoach"})

    status = run_phi_status(adapter)
    ask = run_phi_ask(adapter, "hello")

    assert status["schema_version"] == "2.0"
    assert ask["schema_version"] == "2.0"


def test_pulse_policy_gating_denied_by_default(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.delenv("PHIOS_MCP_ALLOW_PULSE", raising=False)
    data = run_phi_pulse_once(adapter)
    assert data["ok"] is False
    assert data["allowed"] is False
    assert data["error"]["code"] == "PULSE_NOT_PERMITTED"
    assert "schema_version" in data


def test_pulse_policy_gating_allowed(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setenv("PHIOS_MCP_ALLOW_PULSE", "true")
    monkeypatch.setattr("phios.mcp.tools.pulse.run_pulse_once", lambda _a, **_kw: {"field_action": "stabilize"})
    data = run_phi_pulse_once(adapter, checkpoint="cp.json", passphrase="pw")
    assert data["ok"] is True
    assert data["allowed"] is True
    assert data["pulse"]["field_action"] == "stabilize"


def test_history_resources_shapes(monkeypatch):
    monkeypatch.setattr(
        "phios.mcp.resources.history.list_visual_bloom_sessions",
        lambda **_kw: [{"session_id": "s1", "mode": "snapshot", "label": "morning"}],
    )
    monkeypatch.setattr(
        "phios.mcp.resources.history.load_visual_bloom_session",
        lambda _sid, **_kw: {"label": "morning", "mode": "snapshot", "states": [{"stateTimestamp": "t1", "coherenceC": 0.81, "driftBand": "Watch"}]},
    )

    cap = read_recent_capsules_resource(DummyAdapter(), limit=1)
    ses = read_recent_sessions_resource(limit=10)
    snap = read_recent_field_snapshots_resource(limit=10)

    assert cap["count"] == 1
    assert ses["count"] == 1
    assert snap["count"] == 1
    assert "schema_version" in cap and "schema_version" in ses and "schema_version" in snap


def test_history_resources_when_no_data(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.history.list_visual_bloom_sessions", lambda **_kw: [])
    ses = read_recent_sessions_resource(limit=5)
    snap = read_recent_field_snapshots_resource(limit=5)
    assert ses["sessions"] == []
    assert snap["field_snapshots"] == []


def test_server_registers_phase2_history_resources(monkeypatch):
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
    reg = phase1_registry()
    assert "phios://history/recent_capsules" in server.resources
    assert "phios://history/recent_sessions" in server.resources
    assert "phios://history/recent_field_snapshots" in server.resources
    assert "phios://history/recent_capsules" in reg.resources


def test_prompt_contains_schema_metadata(monkeypatch):
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_status_report", lambda _a: {"heart_state": "running"})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_coherence_report", lambda _a: {"C_star": 0.9})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.compute_lt", lambda: {"lt": 0.71})

    prompt = build_field_guidance_prompt(DummyAdapter())
    assert '"schema_version": "2.0"' in prompt
    assert "Hunter's C remains unconfirmed" in prompt
