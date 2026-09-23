from __future__ import annotations

from pathlib import Path

from phios.mcp.tools.agents import run_phi_dispatch_agents
from phios.services.agent_dispatch import build_dispatch_context, run_agentception_plan


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.75,
            "C_star": 0.93,
            "recommended_action": "hold",
            "field_band": "green",
        }

    def capsule_list(self):
        return {"capsules": [1]}


def _forbid_http(*args, **kwargs):
    raise AssertionError("dry-run crossed the HTTP planner boundary")


def test_service_local_plan_never_calls_remote_planner(monkeypatch) -> None:
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "true")
    monkeypatch.setattr("phios.services.agent_dispatch._http_json", _forbid_http)

    context = build_dispatch_context(
        task="preview",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(
        task="preview",
        context=context,
        allow_remote=False,
    )

    assert plan["source"] == "local-dry-run"
    assert plan["planner_available"] is False
    assert plan["remote_planner_attempted"] is False
    assert plan["reason"] == "remote planner disabled by caller"


def test_mcp_dry_run_is_effect_free_under_read_only_policy(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "true")
    monkeypatch.setenv(
        "PHIOS_MCP_CAPABILITIES",
        "read_state,read_history,read_observatory",
    )
    monkeypatch.setattr("phios.services.agent_dispatch._http_json", _forbid_http)

    out = run_phi_dispatch_agents(
        DummyAdapter(),
        task="preview only",
        dry_run=True,
        field_guided=True,
    )

    assert out["ok"] is True
    assert out["allowed"] is True
    assert out["dry_run"] is True
    assert out["plan"]["source"] == "local-dry-run"
    assert out["plan"]["remote_planner_attempted"] is False
    assert out["effects"] == {
        "remote_planner_attempted": False,
        "agent_dispatch_attempted": False,
        "state_persisted": False,
    }
    assert not (tmp_path / ".phios" / "agents").exists()


def test_mcp_live_dispatch_still_requires_dispatch_capability(monkeypatch) -> None:
    monkeypatch.setenv(
        "PHIOS_MCP_CAPABILITIES",
        "read_state,read_history,read_observatory",
    )

    out = run_phi_dispatch_agents(
        DummyAdapter(),
        task="do work",
        dry_run=False,
    )

    assert out["ok"] is False
    assert out["error_code"] == "AGENT_DISPATCH_NOT_PERMITTED"