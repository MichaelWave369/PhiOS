from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.observatory import run_phi_browse_observatory
from phios.mcp.tools.session_archive import run_phi_archive_summary


class DummyAdapter:
    pass


def test_discovery_includes_presets_and_groups(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    payload = build_mcp_discovery_payload(mcp_surface_registry())
    assert "browse_presets" in payload
    assert "resource_groups" in payload
    assert "tool_groups" in payload
    assert "archive_rollups" in payload
    assert "overview" in payload["browse_presets"]["supported"]


def test_browse_preset_resources_shapes(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.browse.read_observatory_dashboard_resource", lambda: {"summary": {"session_count": 0}})
    monkeypatch.setattr("phios.mcp.resources.browse.read_archive_pathways_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.resources.browse.read_recent_sessions_resource", lambda **_kw: {"count": 0, "sessions": []})

    out = read_browse_preset_resource("overview")
    missing = read_browse_preset_resource("nope")

    assert out["schema_version"] == "2.0"
    assert out["available"] is True
    assert "generated_at" in out
    assert missing["available"] is False


def test_preset_aware_tools(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory,read_history")

    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_storyboards_index_resource", lambda **_kw: {"count": 1, "index": [{"id": 1}]})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_dossiers_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_field_libraries_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_shelves_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_reading_rooms_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_study_halls_index_resource", lambda **_kw: {"count": 1, "index": [{"id": 2}]})

    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_pathways_index_resource", lambda **_kw: {"count": 2, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_atlas_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_curricula_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_journey_ensembles_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_route_compares_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_archive_longitudinal_index_resource", lambda **_kw: {"count": 1, "index": {}})

    browse = run_phi_browse_observatory(preset="learning", include_rollups=True)
    archive = run_phi_archive_summary(preset="archive", include_rollups=True, limit=5)

    assert browse["ok"] is True and browse["schema_version"] == "2.0"
    assert browse["preset"] == "learning"
    assert "rollups" in browse

    assert archive["ok"] is True and archive["schema_version"] == "2.0"
    assert archive["preset"] == "archive"
    assert "rollups" in archive


def test_server_registers_phase8_surfaces(monkeypatch):
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

    assert "phios://browse/overview" in server.resources
    assert "phios://browse/learning" in server.resources
    assert "phi_archive_summary" in server.tools
    assert "phios://browse/overview" in reg.resources
