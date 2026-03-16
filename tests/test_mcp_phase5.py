from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.discovery import read_mcp_discovery_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.discovery import run_phi_discovery
from phios.mcp.tools.observatory import run_phi_atlas_summary, run_phi_storyboard_summary


class DummyAdapter:
    def capsule_list(self):
        return {"capsules": []}


def test_discovery_payload_from_registry(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state,read_observatory")
    monkeypatch.delenv("PHIOS_MCP_ALLOW_PULSE", raising=False)
    payload = build_mcp_discovery_payload(mcp_surface_registry())
    assert payload["schema_version"] == "2.0"
    assert "phios://mcp/discovery" in payload["resources"]
    assert "phi_discovery" in payload["tools"]
    assert payload["capabilities"]["pulse"]["enabled"] is False


def test_discovery_resource_and_tool_have_versions(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_state,read_observatory")
    resource = read_mcp_discovery_resource(mcp_surface_registry())
    tool = run_phi_discovery(mcp_surface_registry())
    assert resource["schema_version"] == "2.0"
    assert resource["resource_version"] == "2.0"
    assert tool["schema_version"] == "2.0"
    assert tool["tool_version"] == "2.0"


def test_new_summary_tools_shape_and_sparse_fallback(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "read_observatory")
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_recent_storyboards_resource",
        lambda **_kw: {"count": 0, "storyboards": []},
    )
    monkeypatch.setattr(
        "phios.mcp.tools.observatory.read_observatory_atlas_gallery_resource",
        lambda: {"summary": {"entry_count": 0}, "atlas_gallery": {"gallery_version": "v1"}},
    )

    story = run_phi_storyboard_summary()
    atlas = run_phi_atlas_summary()

    assert story["ok"] is True
    assert story["schema_version"] == "2.0"
    assert story["summary"]["storyboard_count"] == 0
    assert "generated_at" in story

    assert atlas["ok"] is True
    assert atlas["schema_version"] == "2.0"
    assert atlas["summary"]["entry_count"] == 0
    assert "generated_at" in atlas


def test_server_registers_phase5_discovery_and_tools(monkeypatch):
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

    assert "phios://mcp/discovery" in server.resources
    assert "phi_discovery" in server.tools
    assert "phi_storyboard_summary" in server.tools
    assert "phi_atlas_summary" in server.tools
    assert "phios://mcp/discovery" in reg.resources
    assert "phi_discovery" in reg.tools
