from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.policy import resolve_mcp_capabilities, resolve_mcp_profile
from phios.mcp.resources.observatory import (
    read_observatory_dossiers_index_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_shelves_index_resource,
    read_observatory_storyboards_index_resource,
    read_observatory_study_halls_index_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.observatory import run_phi_browse_observatory


class DummyAdapter:
    def capsule_list(self):
        return {"capsules": []}


def test_profile_capability_resolution(monkeypatch):
    monkeypatch.delenv("PHIOS_MCP_CAPABILITIES", raising=False)
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    assert resolve_mcp_profile() == "observer"
    caps, source = resolve_mcp_capabilities()
    assert "prompt_guidance" in caps
    assert source.startswith("env:PHIOS_MCP_PROFILE")


def test_discovery_includes_profile_and_counts(monkeypatch):
    monkeypatch.delenv("PHIOS_MCP_CAPABILITIES", raising=False)
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "read_only")
    payload = build_mcp_discovery_payload(mcp_surface_registry())
    assert payload["profile"] == "read_only"
    assert "resolved_capabilities" in payload
    assert isinstance(payload["resource_counts"], int)
    assert isinstance(payload["tool_counts"], int)
    assert isinstance(payload["prompt_counts"], int)


def test_new_browsing_resources_shape(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_storyboards", lambda **_kw: [{"name": "s"}])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_dossiers", lambda **_kw: [{"name": "d"}])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_field_libraries", lambda **_kw: [{"name": "f"}])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_shelves", lambda **_kw: [{"name": "sh"}])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_reading_rooms", lambda **_kw: [{"name": "rr"}])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_study_halls", lambda **_kw: [{"name": "st"}])

    for payload in (
        read_observatory_storyboards_index_resource(),
        read_observatory_dossiers_index_resource(),
        read_observatory_field_libraries_index_resource(),
        read_observatory_shelves_index_resource(),
        read_observatory_reading_rooms_index_resource(),
        read_observatory_study_halls_index_resource(),
    ):
        assert payload["schema_version"] == "2.0"
        assert "generated_at" in payload
        assert payload["count"] == 1


def test_browse_tool_and_sparse_fallback(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory")
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_storyboards_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_dossiers_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_field_libraries_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_shelves_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_reading_rooms_index_resource", lambda **_kw: {"count": 0, "index": []})
    monkeypatch.setattr("phios.mcp.tools.observatory.read_observatory_study_halls_index_resource", lambda **_kw: {"count": 0, "index": []})

    data = run_phi_browse_observatory()
    assert data["ok"] is True
    assert data["schema_version"] == "2.0"
    assert data["summary"]["storyboards"] == 0


def test_server_registers_phase6_resources_and_tools(monkeypatch):
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

    assert "phios://observatory/storyboards/index" in server.resources
    assert "phios://observatory/shelves/index" in server.resources
    assert "phi_browse_observatory" in server.tools
    assert "phios://observatory/storyboards/index" in reg.resources
