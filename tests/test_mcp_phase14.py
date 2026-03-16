from __future__ import annotations

import sys
import types

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.dashboards import (
    read_dashboards_archive_resource,
    read_dashboards_capstones_resource,
    read_dashboards_discovery_resource,
    read_dashboards_learning_resource,
)
from phios.mcp.resources.families import (
    read_families_capstones_resource,
    read_families_learning_resource,
    read_families_overview_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.discovery import run_phi_discovery_dashboard_summary


class DummyAdapter:
    pass


def test_phase14_dashboard_resources_shape(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    discovery = read_dashboards_discovery_resource(mcp_surface_registry())
    archive = read_dashboards_archive_resource()
    learning = read_dashboards_learning_resource()
    capstones = read_dashboards_capstones_resource()

    for payload in (discovery, archive, learning, capstones):
        assert payload["schema_version"] == "2.0"
        assert payload["resource_version"] == "2.0"
        assert payload["read_only"] is True
        assert "generated_at" in payload
        assert "surface_groups" in payload
        assert "resource_counts" in payload
        assert "tag_coverage" in payload


def test_phase14_family_resources_shape():
    overview = read_families_overview_resource()
    learning = read_families_learning_resource()
    capstones = read_families_capstones_resource()

    assert overview["family"] == "overview"
    assert learning["family"] == "learning"
    assert capstones["family"] == "capstones"
    assert "family_counts" in overview and "catalog_counts" in overview and "map_counts" in overview


def test_phase14_discovery_enhancements_present(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    payload = build_mcp_discovery_payload(mcp_surface_registry())

    assert "dashboard_resources" in payload
    assert "family_resources" in payload
    assert "family_navigation_groups" in payload
    assert "dashboard_surface_counts" in payload
    assert "phios://dashboards/discovery" in payload["dashboard_resources"]
    assert "phios://families/overview" in payload["family_resources"]


def test_phase14_discovery_dashboard_summary_tool(monkeypatch):
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = run_phi_discovery_dashboard_summary(
        mcp_surface_registry(),
        dashboard="learning",
        include_dashboard_counts=True,
        include_family_counts=True,
    )

    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["dashboard"] == "learning"
    assert "dashboard_counts" in out
    assert "family_counts" in out


def test_phase14_server_registers_surfaces(monkeypatch):
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

    assert "phios://dashboards/discovery" in server.resources
    assert "phios://families/overview" in server.resources
    assert "phi_discovery_dashboard_summary" in server.tools
    assert "phios://dashboards/archive" in reg.resources
    assert "phios://families/capstones" in reg.resources
