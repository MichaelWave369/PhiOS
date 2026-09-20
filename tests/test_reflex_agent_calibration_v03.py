from __future__ import annotations

import json

from phios.reflex import PhiReflex
from phios.reflex.dispatch_shadow import observe_dispatch
from phios.services.agent_dispatch import (
    build_dispatch_context,
    dispatch_agentception_run,
    evaluate_agent_run_reflex,
    get_agent_run_status,
)


class DummyAdapter:
    def status(self):
        return {
            "heart_state": "running",
            "anchor_verification_state": "verified",
        }

    def field(self):
        return {
            "C_current": 0.8,
            "field_band": "green",
            "recommended_action": "maintain",
        }

    def capsule_list(self):
        return {"capsules": [1]}


def _make_run(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    task = "build the adapter"
    context = build_dispatch_context(
        task=task,
        adapter=DummyAdapter(),
        field_guided=False,
        arch=None,
        review_panel=False,
    )
    plan = {
        "source": "local-test",
        "planner_available": False,
        "task": task,
        "plan_steps": [{"step": "build", "status": "pending"}],
    }
    shadow = observe_dispatch(
        task=task,
        operational_context=context,
        operational_plan=plan,
        reflex=PhiReflex(),
        external_side_effect=True,
    ).to_dict()
    return dispatch_agentception_run(
        task=task,
        context=context,
        plan=plan,
        stream=False,
        shadow_observations={"phireflex_v0_2": shadow},
    )


def test_agent_run_calibration_is_persisted_with_explicit_labels(
    monkeypatch,
    tmp_path,
):
    run = _make_run(monkeypatch, tmp_path)
    run_id = str(run["run_id"])

    result = evaluate_agent_run_reflex(
        run_id=run_id,
        dispatch_outcome="succeeded",
        observer_label="operator-review",
        evidence_sha256="a" * 64,
        actual_role="builder",
        actual_risk="high",
        system2_needed=True,
        verification_needed=True,
    )

    assert result["ok"] is True
    calibration = result["calibration"]
    assert calibration["schema"] == "phios.reflex_calibration_receipt.v0.3"
    assert calibration["status"] == "scored"
    assert calibration["action_authority"] is False
    assert calibration["execution_authority"] is False

    stored = get_agent_run_status(run_id)
    receipts = stored["reflex_calibration_receipts"]
    assert len(receipts) == 1
    assert receipts[0]["receipt_sha256"] == calibration["receipt_sha256"]


def test_agent_run_can_store_unscored_outcome_without_invented_labels(
    monkeypatch,
    tmp_path,
):
    run = _make_run(monkeypatch, tmp_path)
    run_id = str(run["run_id"])

    result = evaluate_agent_run_reflex(
        run_id=run_id,
        dispatch_outcome="failed",
        observer_label="operator-review",
        evidence_sha256="b" * 64,
    )

    calibration = result["calibration"]
    assert calibration["status"] == "unscored_no_observed_labels"
    assert calibration["baseline"]["scored_dimensions"] == 0
    assert calibration["baseline"]["mean_brier"] is None


def test_missing_shadow_cannot_be_calibrated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    run = dispatch_agentception_run(
        task="plain run",
        context={"task": "plain run"},
        plan={"source": "test"},
        stream=False,
    )

    result = evaluate_agent_run_reflex(
        run_id=str(run["run_id"]),
        dispatch_outcome="succeeded",
        observer_label="operator-review",
        evidence_sha256="c" * 64,
    )

    assert result["ok"] is False
    assert result["error_code"] == "REFLEX_SHADOW_NOT_FOUND"


def test_calibration_event_is_appended(monkeypatch, tmp_path):
    run = _make_run(monkeypatch, tmp_path)
    run_id = str(run["run_id"])

    evaluate_agent_run_reflex(
        run_id=run_id,
        dispatch_outcome="partial",
        observer_label="reviewer",
        evidence_sha256="d" * 64,
        actual_role="builder",
    )

    events_path = (
        tmp_path
        / ".phios"
        / "agents"
        / "runs"
        / f"{run_id}.events.json"
    )
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert events[-1]["event_type"] == "reflex_calibration_recorded"
    assert len(events[-1]["payload"]["receipt_sha256"]) == 64
