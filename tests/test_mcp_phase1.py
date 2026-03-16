from __future__ import annotations

import sys
import types

import pytest

from phios.adapters.phik import PhiKernelAdapterError
from phios.mcp.prompts.field_guidance import build_field_guidance_prompt
from phios.mcp.resources.coherence_lt import read_coherence_lt_resource
from phios.mcp.resources.field_state import read_field_state_resource
from phios.mcp.resources.status import read_system_status_resource
from phios.mcp.server import create_mcp_server, phase1_registry
from phios.mcp.tools.ask import run_phi_ask
from phios.mcp.tools.pulse import run_phi_pulse_once
from phios.mcp.tools.status import run_phi_status


class DummyAdapter:
    pass


def test_phase1_registry_contains_expected_surface():
    reg = phase1_registry()
    assert "phios://field/state" in reg.resources
    assert "phios://coherence/lt" in reg.resources
    assert "phios://system/status" in reg.resources
    assert {"phi_status", "phi_ask", "phi_pulse_once"}.issubset(set(reg.tools))
    assert reg.prompts == ("field_guidance",)


def test_resource_shapes(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr(
        "phios.mcp.resources.field_state.build_coherence_report",
        lambda _a: {"C_current": 0.7, "recommended_action": "hold", "phik_field": {"extra": 1}},
    )
    monkeypatch.setattr(
        "phios.mcp.resources.status.build_status_report",
        lambda _a: {"anchor_verification_state": "verified", "capsule_count": 3},
    )
    monkeypatch.setattr(
        "phios.mcp.resources.coherence_lt.compute_lt",
        lambda: {"lt": 0.8, "system_lt": 0.8, "components": {}, "phb_contribution": 0.0},
    )

    field = read_field_state_resource(adapter)
    status = read_system_status_resource(adapter)
    lt = read_coherence_lt_resource()

    assert field["recommended_action"] == "hold"
    assert "phik_field" in field
    assert status["anchor_verification_state"] == "verified"
    assert lt["lt"] == 0.8


def test_tool_status_shape(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr("phios.mcp.tools.status.build_status_report", lambda _a: {"field_action": "stabilize"})
    monkeypatch.setattr("phios.mcp.tools.status.build_coherence_report", lambda _a: {"C_current": 0.55})
    monkeypatch.setattr("phios.mcp.tools.status.compute_lt", lambda: {"lt": 0.66})
    data = run_phi_status(adapter)
    assert data["status"]["field_action"] == "stabilize"
    assert data["coherence"]["C_current"] == 0.55
    assert data["lt"]["lt"] == 0.66


def test_tool_phi_ask_behavior(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr(
        "phios.mcp.tools.ask.build_ask_report",
        lambda _a, p: {"coach": "SovereignCoach", "body": p, "next_actions": []},
    )
    data = run_phi_ask(adapter, "  grounded guidance ")
    assert data["coach"] == "SovereignCoach"
    assert data["body"] == "grounded guidance"

    with pytest.raises(ValueError):
        run_phi_ask(adapter, "   ")


def test_tool_phi_pulse_once_argument_handling(monkeypatch):
    adapter = DummyAdapter()
    captured: dict[str, object] = {}

    def fake_pulse(_a, *, checkpoint=None, passphrase=None):
        captured["checkpoint"] = checkpoint
        captured["passphrase"] = passphrase
        return {"ok": True}

    monkeypatch.setenv("PHIOS_MCP_ALLOW_PULSE", "true")
    monkeypatch.setattr("phios.mcp.tools.pulse.run_pulse_once", fake_pulse)
    data = run_phi_pulse_once(adapter, checkpoint="./cp.json", passphrase="change-me")
    assert data["ok"] is True
    assert data["allowed"] is True
    assert "pulse" in data
    assert captured == {"checkpoint": "./cp.json", "passphrase": "change-me"}


def test_prompt_output_contains_live_state_and_framing(monkeypatch):
    adapter = DummyAdapter()
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_status_report", lambda _a: {"heart_state": "running"})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_coherence_report", lambda _a: {"C_star": 0.9})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.compute_lt", lambda: {"lt": 0.71})

    prompt = build_field_guidance_prompt(adapter)
    assert "LIVE_STATE_JSON" in prompt
    assert "theoretical C*" in prompt
    assert "Hunter's C remains unconfirmed" in prompt


def test_server_registration_and_graceful_upstream_failure(monkeypatch):
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

    monkeypatch.setattr(
        "phios.mcp.server.read_system_status_resource",
        lambda _a: (_ for _ in ()).throw(PhiKernelAdapterError("downstream failed")),
    )

    server = create_mcp_server(adapter=DummyAdapter())
    assert "phios://field/state" in server.resources
    assert "phi_status" in server.tools
    assert "field_guidance" in server.prompts

    with pytest.raises(RuntimeError, match="upstream call failed"):
        server.resources["phios://system/status"]()
