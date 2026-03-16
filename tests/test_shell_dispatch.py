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
