from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_recommend_atoms_json(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.PhiKernelCLIAdapter",
        lambda: type(
            "A",
            (),
            {
                "status": lambda self: {"heart_state": "running", "anchor_verification_state": "verified"},
                "field": lambda self: {
                    "C_current": 0.8,
                    "distance_to_C_star": 0.01,
                    "geometry_balance": 0.72,
                    "vacuum_proximity": 0.82,
                    "observer_entropy": 0.7,
                    "collector_activity": 0.65,
                    "mirror_alignment": 0.71,
                    "emotion_field": 0.7,
                },
                "capsule_list": lambda self: {"capsules": [1]},
            },
        )(),
    )
    out, code = route_command(["recommend-atoms", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert "atom_overrides" in payload["recommendation"]
