from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.consoles import (
    read_consoles_archive_resource,
    read_consoles_capstones_resource,
    read_consoles_learning_resource,
    read_consoles_navigation_resource,
)
from phios.mcp.resources.families import (
    read_families_dashboard_capstones_resource,
    read_families_dashboard_learning_resource,
    read_families_dashboard_overview_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.discovery import run_phi_navigation_console_summary


class DummyAdapter:
    pass


def test_phase15_console_resources_shape(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    nav = read_consoles_navigation_resource(mcp_surface_registry())
    arc = read_consoles_archive_resource(mcp_surface_registry())
    lrn = read_consoles_learning_resource(mcp_surface_registry())
    cap = read_consoles_capstones_resource(mcp_surface_registry())

    for payload in (nav, arc, lrn, cap):
        assert payload["schema_version"] == "2.0"
        assert payload["resource_version"] == "2.0"
        assert payload["read_only"] is True
        assert "dashboard_counts" in payload
        assert "map_counts" in payload
        assert "availability_flags" in payload


def test_phase15_family_dashboard_resources_shape():
    out = read_families_dashboard_overview_resource()
    lrn = read_families_dashboard_learning_resource()
    cap = read_families_dashboard_capstones_resource()

    assert out["family_dashboard"] == "dashboard_overview"
    assert lrn["family_dashboard"] == "dashboard_learning"
    assert cap["family_dashboard"] == "dashboard_capstones"
    assert "dashboard_counts" in out


def test_phase15_discovery_fields_present(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert "console_resources" in payload
    assert "family_dashboard_resources" in payload
    assert "console_surface_counts" in payload
    assert "family_dashboard_counts" in payload
    assert "phios://consoles/navigation" in payload["console_resources"]
    assert "phios://families/dashboard_overview" in payload["family_dashboard_resources"]


def test_phase15_navigation_console_tool(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = run_phi_navigation_console_summary(
        mcp_surface_registry(),
        console="navigation",
        include_console_counts=True,
        include_family_dashboard_counts=True,
    )
    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["console"] == "navigation"
    assert "console_counts" in out
    assert "family_dashboard_counts" in out


def test_phase15_server_registers_surfaces(monkeypatch):
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

    assert "phios://consoles/navigation" in server.resources
    assert "phios://families/dashboard_overview" in server.resources
    assert "phi_navigation_console_summary" in server.tools
    assert "phios://consoles/archive" in reg.resources
    assert "phios://families/dashboard_capstones" in reg.resources
