from __future__ import annotations

import sys
import types

from phios.mcp.resources.figure_fitness import (
    read_figure_fitness_detail_resource,
    read_figure_recommendation_resource,
    read_figures_fitness_resource,
)
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.figure_fitness import (
    phi_figure_fitness_report,
    phi_record_figure_outcome,
    phi_recommend_figure_for_task,
)


def test_phase80_write_tool_denied_without_capability(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "observer")
    out = phi_record_figure_outcome(
        figure="Architect",
        skills=["planning"],
        run_id="r1",
        pr_grade="A",
        merge_time_minutes=22.0,
        redispatch_count=0,
        issue_closed=True,
        coherence_at_completion=0.82,
        sector_at_dispatch="HG",
    )
    assert out["ok"] is False
    assert out["error_code"] == "FIGURE_FITNESS_WRITE_NOT_PERMITTED"


def test_phase80_tools_and_resources(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_PROFILE", "operator")
    saved = phi_record_figure_outcome(
        figure="Architect",
        skills=["planning"],
        run_id="r2",
        pr_grade="A",
        merge_time_minutes=20.0,
        redispatch_count=0,
        issue_closed=True,
        coherence_at_completion=0.87,
        sector_at_dispatch="HG",
    )
    assert saved["ok"] is True

    report = phi_figure_fitness_report(top=5)
    rec = phi_recommend_figure_for_task(task_key="code_review")
    res_all = read_figures_fitness_resource(top=5)
    res_figure = read_figure_fitness_detail_resource("Architect")
    res_task = read_figure_recommendation_resource("code_review")

    assert report["tool_version"] == "2.0"
    assert rec["tool_version"] == "2.0"
    assert res_all["resource_kind"] == "figures_fitness"
    assert res_figure["resource_kind"] == "figure_fitness_detail"
    assert res_task["resource_kind"] == "figure_recommendation"


def test_phase80_server_registration(monkeypatch):
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

    server = create_mcp_server()
    reg = mcp_surface_registry()
    assert "phi_record_figure_outcome" in server.tools
    assert "phi_figure_fitness_report" in server.tools
    assert "phi_recommend_figure_for_task" in server.tools
    assert "phios://figures/fitness" in server.resources
    assert "phios://figures/fitness/{figure}" in server.resources
    assert "phios://figures/recommendation/{task_key}" in server.resources
    assert "phi_record_figure_outcome" in reg.tools
    assert "phios://figures/fitness" in reg.resources
