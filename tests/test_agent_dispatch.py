from __future__ import annotations

import json

from phios.services.agent_dispatch import (
    build_dispatch_context,
    cancel_agent_run,
    dispatch_agentception_run,
    get_agent_run_status,
    list_agent_runs,
    persist_dispatch_storyboard,
    run_agentception_plan,
    stream_agent_run_events,
)


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.55,
            "C_star": 0.93,
            "recommended_action": "stabilize",
            "field_band": "amber",
        }

    def capsule_list(self):
        return {"capsules": [1, 2, 3]}


def test_dispatch_dry_run_plan_and_field_guided_context(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    context = build_dispatch_context(
        task="test decomposition",
        adapter=DummyAdapter(),
        field_guided=True,
        arch="mesh",
        review_panel=True,
    )
    plan = run_agentception_plan(task="test decomposition", context=context)

    assert context["arch"] == "mesh"
    assert "field_state" in context
    assert plan["source"] == "local-fallback"
    assert isinstance(plan.get("plan_steps"), list)


def test_runs_status_kill_and_events(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="agent run",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="agent run", context=context)
    run = dispatch_agentception_run(task="agent run", context=context, plan=plan, stream=False)
    run_id = str(run["run_id"])

    runs = list_agent_runs(active_only=True)
    assert any(str(item.get("run_id")) == run_id for item in runs)

    status = get_agent_run_status(run_id)
    assert status["run_id"] == run_id

    killed = cancel_agent_run(run_id)
    assert killed["ok"] is True

    events = stream_agent_run_events(run_id)
    assert len(events) >= 2


def test_storyboard_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="persist storyboard",
        adapter=DummyAdapter(),
        field_guided=True,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="persist storyboard", context=context)
    run = dispatch_agentception_run(task="persist storyboard", context=context, plan=plan, stream=False)
    run_id = str(run["run_id"])
    result = persist_dispatch_storyboard(run=run, plan=plan, events=stream_agent_run_events(run_id))

    sb_name = result["storyboard_name"]
    sb_path = tmp_path / ".phios" / "journal" / "visual_bloom" / "storyboards" / f"{sb_name}.json"
    assert sb_path.exists()
    payload = json.loads(sb_path.read_text(encoding="utf-8"))
    assert payload["storyboard_name"] == sb_name


def test_dispatch_run_persists_shadow_observations_without_planner_contamination(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    context = build_dispatch_context(
        task="shadow dispatch",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = run_agentception_plan(task="shadow dispatch", context=context)
    shadow = {
        "phireflex_v0_2": {
            "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
            "receipt_sha256": "a" * 64,
        }
    }

    assert "reflex" not in json.dumps(context).lower()
    assert "reflex" not in json.dumps(plan).lower()

    run = dispatch_agentception_run(
        task="shadow dispatch",
        context=context,
        plan=plan,
        stream=False,
        shadow_observations=shadow,
    )

    assert run["shadow_observations"] == shadow
    assert "reflex" not in json.dumps(run["context"]).lower()
    assert "reflex" not in json.dumps(run["plan"]).lower()


def test_remote_dispatch_payload_excludes_reflex_shadow(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "true")
    captured = []

    def fake_http_json(url, *, method="GET", payload=None, timeout_s=10.0):
        captured.append({"url": url, "method": method, "payload": payload})
        return True, {"run_id": "remote-1", "status": "running"}

    monkeypatch.setattr(
        "phios.services.agent_dispatch._http_json",
        fake_http_json,
    )

    context = build_dispatch_context(
        task="remote shadow dispatch",
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = {
        "source": "local-test",
        "planner_available": True,
        "plan_steps": [{"step": "work", "status": "pending"}],
    }
    shadow = {
        "phireflex_v0_2": {
            "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
            "receipt_sha256": "b" * 64,
        }
    }

    run = dispatch_agentception_run(
        task="remote shadow dispatch",
        context=context,
        plan=plan,
        stream=False,
        shadow_observations=shadow,
    )

    assert run["shadow_observations"] == shadow
    assert len(captured) == 1
    outbound = captured[0]["payload"]
    assert isinstance(outbound, dict)
    assert set(outbound) == {"task", "context", "plan", "stream"}
    assert "reflex" not in json.dumps(outbound).lower()
