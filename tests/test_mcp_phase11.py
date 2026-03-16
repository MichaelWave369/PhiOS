from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.resources.capstones import read_capstones_syllabi_rollup_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.session_archive import run_phi_capstone_summary


class DummyAdapter:
    pass


def test_capstone_rollup_shape(monkeypatch):
    monkeypatch.setattr(
        "phios.mcp.resources.capstones.list_visual_bloom_syllabi",
        lambda: [{"title": "Capstone Syllabus", "tags": ["track"], "sector": "HG"}],
    )
    out = read_capstones_syllabi_rollup_resource()
    assert out["schema_version"] == "2.0"
    assert out["count"] == 1
    assert out["read_only"] is True
    assert "generated_at" in out


def test_discovery_and_browse_families(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_syllabi_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_atlas_cohorts_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_dossiers_rollup_family_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_capstones_storyboards_rollup_family_resource", lambda: {"count": 0})

    browse = read_browse_preset_resource("capstones")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert browse["available"] is True
    assert "capstone_rollups" in payload
    assert "collection_family_rollups" in payload
    assert "learning_browse_families" in payload
    assert "capstone_surface_counts" in payload


def test_capstone_summary_tool(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history")
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_syllabi_rollup_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_atlas_cohorts_rollup_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_field_libraries_rollup_family_resource", lambda: {"count": 3})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_dossiers_rollup_family_resource", lambda: {"count": 4})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_capstones_storyboards_rollup_family_resource", lambda: {"count": 5})

    out = run_phi_capstone_summary()
    assert out["ok"] is True
    assert out["schema_version"] == "2.0"
    assert out["summary"]["total_capstone_items"] == 15


def test_server_registers_phase11_surfaces(monkeypatch):
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

    assert "phios://capstones/syllabi/rollup" in server.resources
    assert "phios://browse/capstones" in server.resources
    assert "phi_capstone_summary" in server.tools
    assert "phios://capstones/storyboards/rollup_family" in reg.resources
