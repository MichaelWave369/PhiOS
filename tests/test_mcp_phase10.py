from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.browse import read_browse_preset_resource
from phios.mcp.resources.programs import read_programs_curricula_rollup_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.session_archive import run_phi_curation_summary, run_phi_program_summary


class DummyAdapter:
    pass


def test_program_rollup_resource_shape(monkeypatch):
    monkeypatch.setattr(
        "phios.mcp.resources.programs.list_visual_bloom_curricula",
        lambda: [{"title": "Curriculum A", "tags": ["learning"], "sector": "HG"}],
    )
    out = read_programs_curricula_rollup_resource()
    assert out["schema_version"] == "2.0"
    assert out["count"] == 1
    assert out["read_only"] is True
    assert "generated_at" in out


def test_program_discovery_and_browse_presets(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    monkeypatch.setattr("phios.mcp.resources.browse.read_programs_curricula_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_programs_syllabi_rollup_resource", lambda: {"count": 0})
    monkeypatch.setattr("phios.mcp.resources.browse.read_archive_curricula_index_resource", lambda **_kw: {"count": 0, "index": []})

    browse = read_browse_preset_resource("curricula")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert browse["available"] is True
    assert "program_rollups" in payload
    assert "learning_groups" in payload
    assert "program_surface_counts" in payload


def test_program_and_curation_tools(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_history")
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_curricula_rollup_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_study_halls_rollup_resource", lambda: {"count": 1})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_thematic_pathways_rollup_resource", lambda: {"count": 3})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_syllabi_rollup_resource", lambda: {"count": 2})
    monkeypatch.setattr("phios.mcp.tools.session_archive.read_programs_journey_ensembles_rollup_resource", lambda: {"count": 1})

    monkeypatch.setattr("phios.mcp.tools.session_archive.run_phi_collection_summary", lambda: {"summary": {"total_collection_items": 5}})

    program = run_phi_program_summary()
    curation = run_phi_curation_summary()

    assert program["ok"] is True and program["schema_version"] == "2.0"
    assert curation["ok"] is True and curation["schema_version"] == "2.0"
    assert curation["summary"]["combined_total"] == 14


def test_server_registers_phase10_surfaces(monkeypatch):
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

    assert "phios://programs/curricula/rollup" in server.resources
    assert "phios://browse/learning_tracks" in server.resources
    assert "phi_program_summary" in server.tools
    assert "phi_curation_summary" in server.tools
    assert "phios://programs/thematic_pathways/rollup" in reg.resources
