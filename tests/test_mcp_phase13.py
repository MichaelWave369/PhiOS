from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.resources.maps import read_learning_map_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.session_archive import run_phi_learning_map_summary


class DummyAdapter:
    pass


def test_learning_map_resource_shape(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.maps.read_catalog_learning_resource", lambda: {"count": 1, "families": ["curricula"], "artifact_family_counts": {"curricula": 1}, "tag_coverage": ["a"], "dominant_sector_counts": {"HG": 1}, "recent_titles": ["X"], "availability": {"route": False, "longitudinal": False, "diagnostics": False}})
    monkeypatch.setattr("phios.mcp.resources.maps.read_catalog_programs_resource", lambda: {"count": 1, "artifact_family_counts": {"programs": 1}, "tag_coverage": [], "dominant_sector_counts": {}, "recent_titles": [], "availability": {}})
    monkeypatch.setattr("phios.mcp.resources.maps.read_catalog_capstones_resource", lambda: {"count": 0, "artifact_family_counts": {}, "tag_coverage": [], "dominant_sector_counts": {}, "recent_titles": [], "availability": {}})
    monkeypatch.setattr("phios.mcp.resources.maps.read_catalog_collections_resource", lambda: {"count": 0, "artifact_family_counts": {}, "tag_coverage": [], "dominant_sector_counts": {}, "recent_titles": [], "availability": {}})

    out = read_learning_map_resource()
    assert out["schema_version"] == "2.0"
    assert out["map"] == "learning"
    assert out["read_only"] is True
    assert "generated_at" in out


def test_phase13_discovery_and_browse(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    monkeypatch.setattr("phios.mcp.resources.browse.read_learning_map_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_map_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_programs_map_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_collections_map_resource", lambda: {"count": 0})

    browse = read_browse_preset_resource("learning_maps")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert browse["available"] is True
    assert "learning_maps" in payload
    assert "archive_family_groups" in payload
    assert "cross_catalog_groups" in payload
    assert "map_surface_counts" in payload


def test_learning_map_summary_tool(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history")
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_learning_map_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_map_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_map_resource", lambda: {"count": 3})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_collections_map_resource", lambda: {"count": 4})

    out = run_phi_learning_map_summary(include_map_counts=True)
    assert out["ok"] is True
    assert out["schema_version"] == "2.0"
    assert out["summary"]["combined_count"] == 10


def test_server_registers_phase13_surfaces(monkeypatch):
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

    assert "phios://maps/learning" in server.resources
    assert "phios://browse/learning_maps" in server.resources
    assert "phi_learning_map_summary" in server.tools
    assert "phios://maps/programs" in reg.resources
