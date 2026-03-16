from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from phios.mcp.resources.sessions import (
    read_sessions_current_resource,
    read_sessions_recent_checkins_resource,
    read_sessions_recent_reports_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.session_archive import run_phi_archive_summary, run_phi_session_summary


class DummyAdapter:
    pass


def test_session_resources_shape(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.sessions.build_session_start_report", lambda _a: {"session_state": "steady"})
    monkeypatch.setattr("phios.mcp.resources.sessions.build_session_checkin_report", lambda _a: {"session_state": "steady", "recommended_action": "maintain", "next_step": "hold"})
    monkeypatch.setattr("phios.mcp.resources.sessions.list_visual_bloom_sessions", lambda **_kw: [{"session_id": "s1", "mode": "snapshot"}])

    current = read_sessions_current_resource(DummyAdapter())
    checkins = read_sessions_recent_checkins_resource(limit=5)
    reports = read_sessions_recent_reports_resource(limit=5)

    assert current["schema_version"] == "2.0"
    assert checkins["count"] == 1
    assert reports["count"] == 1
    assert "generated_at" in current and "generated_at" in checkins and "generated_at" in reports


def test_archive_resources_shape(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.archive.list_visual_bloom_pathways", lambda **_kw: [{"pathway_name": "p1"}])
    monkeypatch.setattr("phios.mcp.resources.archive.list_visual_bloom_atlas_cohorts", lambda **_kw: [{"cohort_name": "a1"}])
    monkeypatch.setattr("phios.mcp.resources.archive.list_visual_bloom_curricula", lambda **_kw: [{"curriculum_name": "c1"}])
    monkeypatch.setattr("phios.mcp.resources.archive.list_visual_bloom_journey_ensembles", lambda **_kw: [{"journey_ensemble_name": "j1"}])
    monkeypatch.setattr("phios.mcp.resources.archive.build_visual_bloom_dashboard_model", lambda **_kw: {"recent_route_compares": [{"id": "r1"}]})
    monkeypatch.setattr("phios.mcp.resources.archive.build_visual_bloom_longitudinal_summary", lambda **_kw: {"session_count": 1})

    payloads = [
        read_archive_pathways_index_resource(),
        read_archive_atlas_index_resource(),
        read_archive_curricula_index_resource(),
        read_archive_journey_ensembles_index_resource(),
        read_archive_route_compares_index_resource(),
        read_archive_longitudinal_index_resource(),
    ]
    for p in payloads:
        assert p["schema_version"] == "2.0"
        assert "generated_at" in p


def test_session_archive_tools(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history")
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_sessions_current_resource", lambda _a: {"summary": {"session_state": "steady"}})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_sessions_recent_checkins_resource", lambda **_kw: {"count": 0, "checkins": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_sessions_recent_reports_resource", lambda **_kw: {"count": 0, "reports": []})

    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_pathways_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_atlas_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_curricula_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_journey_ensembles_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_route_compares_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_longitudinal_index_resource", lambda **_kw: {"count": 0, "index": {}})

    sess = run_phi_session_summary(DummyAdapter())
    arch = run_phi_archive_summary()
    assert sess["ok"] is True and sess["schema_version"] == "2.0"
    assert arch["ok"] is True and arch["schema_version"] == "2.0"


def test_discovery_includes_session_archive_surfaces(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    payload = build_mcp_discovery_payload(mcp_surface_registry())
    assert "phios://sessions/current" in payload["session_resources"]
    assert "phios://archive/pathways/index" in payload["archive_resources"]


def test_server_registers_phase7_surfaces(monkeypatch):
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
    assert "phios://sessions/current" in server.resources
    assert "phios://archive/pathways/index" in server.resources
    assert "phi_session_summary" in server.tools
    assert "phi_archive_summary" in server.tools
