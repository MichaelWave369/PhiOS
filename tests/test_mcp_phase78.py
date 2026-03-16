from __future__ import annotations

import sys
import types

from phios.mcp.resources.reviews import read_review_panel_resource, read_reviews_recent_resource
from phios.mcp.server import create_mcp_server, mcp_surface_registry
from phios.mcp.tools.review import phi_review_coherence_gate


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.75,
            "distance_to_C_star": 0.15,
            "recommended_action": "maintain",
            "field_band": "green",
            "fragmentation_score": 0.12,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def _grades() -> list[dict[str, object]]:
    return [{"reviewer": "A", "grade": 0.7}, {"reviewer": "B", "grade": 0.85}]


def test_phase78_tool_shape_and_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    bad = phi_review_coherence_gate(
        DummyAdapter(),
        round=0,
        reviewer_grades=_grades(),
        reviewer_critiques=["x"],
    )
    assert bad["ok"] is False

    out = phi_review_coherence_gate(
        DummyAdapter(),
        round=1,
        reviewer_grades=_grades(),
        reviewer_critiques=["looks fine"],
        panel_id="panel-a",
        pr_number=100,
        persist=True,
    )
    assert out["ok"] is True
    assert out["tool_version"] == "2.0"
    assert out["result"]["action"] in {"continue", "mediate", "converged"}


def test_phase78_resources(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _ = phi_review_coherence_gate(
        DummyAdapter(),
        round=1,
        reviewer_grades=_grades(),
        reviewer_critiques=["nits"],
        panel_id="panel-b",
        persist=True,
    )
    recent = read_reviews_recent_resource(10)
    panel = read_review_panel_resource("panel-b")
    assert recent["resource_kind"] == "reviews_recent"
    assert panel["resource_kind"] == "review_panel"


def test_phase78_server_registration(monkeypatch):
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
    assert "phi_review_coherence_gate" in server.tools
    assert "phios://reviews/recent" in server.resources
    assert "phios://reviews/{panel_id}" in server.resources
    assert "phi_review_coherence_gate" in reg.tools
    assert "phios://reviews/recent" in reg.resources
