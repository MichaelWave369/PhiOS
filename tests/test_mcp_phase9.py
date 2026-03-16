from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.resources.collections import read_field_libraries_rollup_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.session_archive import run_phi_collection_summary


class DummyAdapter:
    pass


def test_collection_rollup_resource_shape(monkeypatch):
    monkeypatch.setattr(
        "phios.mcp.resources.collections.list_visual_bloom_field_libraries",
        lambda: [{"title": "Library A", "tags": ["bio"], "sector": "HG"}],
    )
    out = read_field_libraries_rollup_resource()
    assert out["schema_version"] == "2.0"
    assert out["count"] == 1
    assert out["read_only"] is True
    assert "generated_at" in out


def test_learning_browse_preset_and_discovery(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    monkeypatch.setattr("phios.mcp.resources.browse.read_archive_curricula_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.resources.browse.read_archive_journey_ensembles_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.resources.browse.read_observatory_study_halls_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.resources.browse.read_curricula_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_journey_ensembles_rollup_resource", lambda: {"count": 0})

    browse = read_browse_preset_resource("learning_paths")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert browse["schema_version"] == "2.0"
    assert browse["available"] is True
    assert "views" in browse
    assert "collection_rollups" in payload
    assert "learning_presets" in payload
    assert "browse_surface_counts" in payload


def test_collection_summary_tool(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history")
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_field_libraries_rollup_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_shelves_rollup_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_reading_rooms_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_study_halls_rollup_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_curricula_rollup_resource", lambda: {"count": 3})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_journey_ensembles_rollup_resource", lambda: {"count": 4})

    out = run_phi_collection_summary()
    assert out["ok"] is True
    assert out["schema_version"] == "2.0"
    assert out["summary"]["total_collection_items"] == 11


def test_server_registers_phase9_surfaces(monkeypatch):
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

    assert "phios://collections/field_libraries/rollup" in server.resources
    assert "phios://browse/learning_paths" in server.resources
    assert "phi_collection_summary" in server.tools
    assert "phios://collections/curricula/rollup" in reg.resources
