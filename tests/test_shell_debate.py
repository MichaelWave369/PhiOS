from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_debate_gate_json(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {
                    "C_current": 0.7,
                    "distance_to_C_star": 0.2,
                    "field_band": "amber",
                    "recommended_action": "stabilize",
                    "fragmentation_score": 0.2,
                },
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    positions = '[{"figure":"Architect","claim":"scope","stance":"pro","support":0.8}]'
    out, code = route_command([
        "debate",
        "gate",
        "--session-id",
        "shell-session",
        "--round",
        "2",
        "--positions",
        positions,
        "--threshold",
        "0.9",
        "--json",
    ])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["result"]["action"] in {"continue", "converged", "deadlock"}
