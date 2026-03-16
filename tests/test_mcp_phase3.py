from __future__ import annotations

import sys
import types

from phios.mcp.prompts.field_guidance import build_field_guidance_prompt
from phios.mcp.resources.observatory import (
    read_observatory_atlas_gallery_resource,
    read_observatory_dashboard_resource,
    read_observatory_index_resource,
    read_observatory_recent_dossiers_resource,
    read_observatory_recent_field_libraries_resource,
    read_observatory_recent_storyboards_resource,
)
from phios.mcp.server import create_mcp_server, phase1_registry


def test_observatory_index_shape_and_schema():
    payload = read_observatory_index_resource()
    assert payload["schema_version"] == "2.0"
    assert payload["resource_count"] >= 1
    assert "generated_at" in payload
    assert isinstance(payload["resources"], list)


def test_observatory_dashboard_and_atlas_shapes(monkeypatch):
    monkeypatch.setattr(
        "phios.mcp.resources.observatory.build_visual_bloom_dashboard_model",
        lambda **_kw: {"generated_at": "t", "sessions": [{"id": "s1"}], "results": [{"id": "r1"}]},
    )
    monkeypatch.setattr(
        "phios.mcp.resources.observatory.build_visual_bloom_atlas_gallery_model",
        lambda **_kw: {"entry_count": 2, "entries": [{"id": "a1"}, {"id": "a2"}]},
    )

    dash = read_observatory_dashboard_resource()
    atlas = read_observatory_atlas_gallery_resource()

    assert dash["schema_version"] == "2.0"
    assert dash["summary"]["session_count"] == 1
    assert "generated_at" in dash

    assert atlas["schema_version"] == "2.0"
    assert atlas["summary"]["entry_count"] == 2
    assert "generated_at" in atlas


def test_recent_observatory_resources_sparse_fallback(monkeypatch):
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_storyboards", lambda **_kw: [])
    monkeypatch.setattr("phios.mcp.resources.observatory.list_visual_bloom_dossiers", lambda **_kw: [])
    monkeypatch.setattr("phios.mcp.resources.observatory.build_visual_bloom_field_library_index", lambda **_kw: [])

    storyboards = read_observatory_recent_storyboards_resource(limit=10)
    dossiers = read_observatory_recent_dossiers_resource(limit=10)
    libs = read_observatory_recent_field_libraries_resource(limit=10)

    assert storyboards["storyboards"] == []
    assert dossiers["dossiers"] == []
    assert libs["field_libraries"] == []
    assert "generated_at" in storyboards and "generated_at" in dossiers and "generated_at" in libs


def test_server_registers_phase3_resources(monkeypatch):
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

    class DummyAdapter:
        pass

    server = create_mcp_server(adapter=DummyAdapter())
    reg = phase1_registry()

    assert "phios://observatory/index" in server.resources
    assert "phios://observatory/dashboard" in server.resources
    assert "phios://observatory/atlas_gallery" in server.resources
    assert "phios://observatory/storyboards/recent" in server.resources
    assert "phios://observatory/dossiers/recent" in server.resources
    assert "phios://observatory/field_libraries/recent" in server.resources
    assert "phios://observatory/index" in reg.resources


def test_prompt_mentions_observatory_resources(monkeypatch):
    class DummyAdapter:
        pass

    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_status_report", lambda _a: {"heart_state": "running"})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.build_coherence_report", lambda _a: {"C_star": 0.9})
    monkeypatch.setattr("phios.mcp.prompts.field_guidance.compute_lt", lambda: {"lt": 0.71})

    prompt = build_field_guidance_prompt(DummyAdapter())
    assert "phios://observatory/index" in prompt
    assert "Hunter's C remains unconfirmed" in prompt
