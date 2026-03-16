from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_recommend_arch_json(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {
                    "C_current": 0.82,
                    "distance_to_C_star": 0.0,
                    "field_band": "green",
                    "recommended_action": "maintain",
                    "fragmentation_score": 0.11,
                },
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    out, code = route_command(["recommend-arch", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert "recommendation" in payload
