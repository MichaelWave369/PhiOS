from __future__ import annotations

import sys
import types

from phios.mcp.policy import (
    CAP_PULSE_ONCE,
    CAP_READ_HISTORY,
    CAP_READ_OBSERVATORY,
    is_capability_allowed,
    resolve_mcp_capabilities,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.observatory import (
    run_phi_library_summary,
    run_phi_observatory_summary,
    run_phi_recent_activity,
)


class DummyAdapter:
    def capsule_list(self):
        return {"capsules": []}


def test_capability_resolution_defaults_and_env(monkeypatch):
    monkeypatch.delenv("PHIOS_MCP_CAPABILITIES", raising=False)
    caps, source = resolve_mcp_capabilities()
    assert CAP_READ_OBSERVATORY in caps
    assert CAP_READ_HISTORY in caps
    assert CAP_PULSE_ONCE not in caps
    assert source == "default-safe"

    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state,pulse_once")
    caps2, source2 = resolve_mcp_capabilities()
    assert "read_state" in caps2 and CAP_PULSE_ONCE in caps2
    assert source2 == "env:PHIOS_MCP_CAPABILITIES"


def test_capability_allow_deny(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory")
    ok = is_capability_allowed(CAP_READ_OBSERVATORY)
    denied = is_capability_allowed(CAP_READ_HISTORY)
    assert ok.allowed is True
    assert denied.allowed is False
    assert denied.capability_scope == CAP_READ_HISTORY


def test_summary_tools_shapes_and_schema(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory,read_history")
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_dashboard_resource",
        lambda: {"summary": {"session_count": 1}, "dashboard": {"recent_shelves": [], "recent_reading_rooms": [], "recent_study_halls": []}},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_atlas_gallery_resource",
        lambda: {"summary": {"entry_count": 2}},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_recent_storyboards_resource",
        lambda **_kw: {"count": 3, "storyboards": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_recent_dossiers_resource",
        lambda **_kw: {"count": 4, "dossiers": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_recent_field_libraries_resource",
        lambda **_kw: {"count": 5, "field_libraries": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_recent_capsules_resource",
        lambda *_a, **_kw: {"count": 0, "capsules": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_recent_sessions_resource",
        lambda **_kw: {"count": 0, "sessions": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_recent_field_snapshots_resource",
        lambda **_kw: {"count": 0, "field_snapshots": []},
    )

    obs = run_phi_observatory_summary()
    rec = run_phi_recent_activity(DummyAdapter())
    lib = run_phi_library_summary()

    assert obs["ok"] is True and obs["schema_version"] == "2.0"
    assert rec["ok"] is True and rec["schema_version"] == "2.0"
    assert lib["ok"] is True and lib["schema_version"] == "2.0"
    assert "generated_at" in obs and "generated_at" in rec and "generated_at" in lib


def test_summary_tools_denied_when_capability_missing(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state")
    obs = run_phi_observatory_summary()
    rec = run_phi_recent_activity(DummyAdapter())
    lib = run_phi_library_summary()

    assert obs["ok"] is False and obs["allowed"] is False
    assert rec["ok"] is False and rec["allowed"] is False
    assert lib["ok"] is False and lib["allowed"] is False
    assert obs["error_code"] == "OBSERVATORY_SUMMARY_NOT_PERMITTED"


def test_server_registers_phase4_tools(monkeypatch):
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

    assert "phi_observatory_summary" in server.tools
    assert "phi_recent_activity" in server.tools
    assert "phi_library_summary" in server.tools
    assert "phi_observatory_summary" in reg.tools


def test_sparse_no_data_fallback(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory,read_history")
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_dashboard_resource",
        lambda: {"summary": {"session_count": 0}, "dashboard": {}},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_atlas_gallery_resource",
        lambda: {"summary": {"entry_count": 0}},
    )
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_recent_storyboards_resource", lambda **_kw: {"count": 0, "storyboards": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_recent_dossiers_resource", lambda **_kw: {"count": 0, "dossiers": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_recent_field_libraries_resource", lambda **_kw: {"count": 0, "field_libraries": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_recent_capsules_resource", lambda *_a, **_kw: {"count": 0, "capsules": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_recent_sessions_resource", lambda **_kw: {"count": 0, "sessions": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_recent_field_snapshots_resource", lambda **_kw: {"count": 0, "field_snapshots": []})

    assert run_phi_observatory_summary()["summary"]["atlas_entries"] == 0
    assert run_phi_recent_activity(DummyAdapter())["summary"]["session_count"] == 0
    assert run_phi_library_summary()["summary"]["field_library_count"] == 0
