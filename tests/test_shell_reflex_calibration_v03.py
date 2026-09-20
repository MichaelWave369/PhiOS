from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_agents_reflex_evaluate_command_passes_explicit_observations(monkeypatch):
    captured = {}

    def fake_evaluate(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "run_id": kwargs["run_id"],
            "calibration": {
                "schema": "phios.reflex_calibration_receipt.v0.3",
                "status": "scored",
            },
        }

    monkeypatch.setattr(
        "phios.shell.phi_commands.evaluate_agent_run_reflex",
        fake_evaluate,
    )

    out, code = route_command(
        [
            "agents",
            "reflex-evaluate",
            "run_123",
            "--outcome",
            "succeeded",
            "--observer",
            "operator",
            "--evidence-sha",
            "a" * 64,
            "--role",
            "builder",
            "--risk",
            "elevated",
            "--system2-needed",
            "yes",
            "--verification-needed",
            "no",
        ]
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert captured["run_id"] == "run_123"
    assert captured["actual_role"] == "builder"
    assert captured["actual_risk"] == "elevated"
    assert captured["system2_needed"] is True
    assert captured["verification_needed"] is False


def test_agents_reflex_evaluate_rejects_ambiguous_boolean(monkeypatch):
    out, code = route_command(
        [
            "agents",
            "reflex-evaluate",
            "run_123",
            "--outcome",
            "succeeded",
            "--observer",
            "operator",
            "--evidence-sha",
            "a" * 64,
            "--system2-needed",
            "maybe",
        ]
    )

    assert code == 0
    assert "--system2-needed must be yes or no" in out
