from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.resources.catalogs import read_catalog_learning_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.observatory import run_phi_browse_observatory
from phios.mcp.tools.session_archive import run_phi_catalog_summary


class DummyAdapter:
    pass


def test_catalog_resource_shape(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.catalogs.list_visual_bloom_curricula", lambda: [{"title": "C1", "tags": ["learn"], "family": "curricula"}])
    monkeypatch.setattr("phios.mcp.resources.catalogs.list_visual_bloom_study_halls", lambda: [])
    monkeypatch.setattr("phios.mcp.resources.catalogs.list_visual_bloom_thematic_pathways", lambda: [])

    out = read_catalog_learning_resource()
    assert out["schema_version"] == "2.0"
    assert out["read_only"] is True
    assert "generated_at" in out
    assert "families" in out


def test_family_browse_presets_and_discovery(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    monkeypatch.setattr("phios.mcp.resources.browse.read_catalog_capstones_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_syllabi_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_atlas_cohorts_rollup_resource", lambda: {"count": 0})

    browse = read_browse_preset_resource("capstone_families")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert browse["available"] is True
    assert "catalog_resources" in payload
    assert "observatory_family_groups" in payload
    assert "catalog_surface_counts" in payload
    assert "browse_family_groups" in payload


def test_catalog_summary_and_browse_tool_enhancement(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history,read_observatory")

    monkeypatch.setattr("phios.mcp.tools.session_archive.read_catalog_learning_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_catalog_capstones_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_catalog_programs_resource", lambda: {"count": 3})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_catalog_collections_resource", lambda: {"count": 4})

    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_storyboards_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_dossiers_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_field_libraries_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_shelves_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_reading_rooms_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_study_halls_index_resource", lambda **_kw: {"count": 1, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_catalog_learning_resource", lambda: {"count": 9})

    summary = run_phi_catalog_summary()
    browse = run_phi_browse_observatory(family_group="libraries", catalog="learning", include_catalog_counts=True)

    assert summary["ok"] is True and summary["summary"]["total_items"] == 10
    assert browse["ok"] is True and "catalogs" in browse and "catalog_counts" in browse


def test_server_registers_phase12_surfaces(monkeypatch):
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

    assert "phios://catalogs/learning" in server.resources
    assert "phios://browse/observatory_families" in server.resources
    assert "phi_catalog_summary" in server.tools
    assert "phios://catalogs/capstones" in reg.resources
