from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_dispatch_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {"C_current": 0.9, "field_band": "green", "recommended_action": "maintain"},
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    out, code = route_command(["dispatch", "plan", "task", "--dry-run", "--field-guided"])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True


def test_shell_dispatch_coherence_gate_block(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {"C_current": 0.2, "field_band": "red", "recommended_action": "stabilize"},
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    out, code = route_command(["dispatch", "plan", "task", "--dry-run", "--field-guided", "--coherence-gate", "0.7"])
    assert code == 0
    payload = json.loads(out)
    assert payload["error_code"] == "COHERENCE_GATE_BLOCKED"


def test_shell_dispatch_reflex_shadow_is_advisory_and_isolated(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {
                    "heart_state": "running",
                    "anchor_verification_state": "verified",
                },
                "field": lambda self: {
                    "C_current": 0.9,
                    "field_band": "green",
                    "recommended_action": "maintain",
                },
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )

    out, code = route_command(
        [
            "dispatch",
            "build",
            "adapter",
            "--dry-run",
            "--reflex-shadow",
        ]
    )

    assert code == 0
    payload = json.loads(out)
    shadow = payload["reflex_shadow"]
    assert shadow["schema"] == "phios.reflex_dispatch_shadow_receipt.v0.2"
    assert shadow["planner_influenced_by_reflex"] is False
    assert shadow["action_authority"] is False
    assert shadow["execution_authority"] is False
    assert shadow["reflex_receipt"]["shadow_status"] == "unavailable"
    assert "reflex" not in json.dumps(payload["context"]).lower()
    assert "reflex" not in json.dumps(payload["plan"]).lower()
