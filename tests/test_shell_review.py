from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_review_gate_json(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {
                    "C_current": 0.74,
                    "distance_to_C_star": 0.16,
                    "field_band": "green",
                    "recommended_action": "maintain",
                    "fragmentation_score": 0.1,
                },
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    grades = '[{"reviewer":"A","grade":0.7},{"reviewer":"B","grade":0.9}]'
    critiques = '["need tests","security check"]'
    out, code = route_command([
        "review",
        "gate",
        "--round",
        "2",
        "--reviewer-grades",
        grades,
        "--reviewer-critiques",
        critiques,
        "--panel-id",
        "shell-panel",
        "--json",
    ])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["result"]["action"] in {"continue", "mediate", "converged"}
