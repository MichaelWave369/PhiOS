from __future__ import annotations

import json
import subprocess

import pytest

from phios.adapters.phik import PhiKernelCLIAdapter, PhiKernelUnavailableError
from phios.shell.phi_router import route_command


def test_phi_status_parses_wrapped_phik_status_json(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_status_report",
        lambda *_: {
            "anchor_verification_state": "verified",
            "heart_state": "running",
            "field_action": "hold",
            "field_drift_band": "green",
            "capsule_count": 2,
        },
    )
    out, code = route_command(["status", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["anchor_verification_state"] == "verified"


def test_phi_coherence_parses_wrapped_phik_field_json(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_coherence_report",
        lambda *_: {
            "C_current": 0.62,
            "C_star": 0.9,
            "distance_to_C_star": 0.28,
            "phi_flow": 0.41,
            "lambda_node": 0.38,
            "sigma_feedback": 0.11,
            "fragmentation_score": 0.09,
            "recommended_action": "stabilize",
        },
    )
    out, code = route_command(["coherence", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["recommended_action"] == "stabilize"


def test_phi_ask_parses_wrapped_phik_ask_json(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_ask_report",
        lambda *_: {
            "coach": "SovereignCoach",
            "field_action": "maintain",
            "field_band": "green",
            "safety_posture": "safe",
            "route_reason": "deterministic",
            "body": "Begin with a stable baseline.",
            "next_actions": ["phi status", "phi coherence"],
        },
    )
    out, code = route_command(["ask", "How should I begin?", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["coach"] == "SovereignCoach"


def test_phi_sovereign_export_writes_valid_json_bundle(monkeypatch, tmp_path):
    output = tmp_path / "bundle.json"

    def fake_export(_, path: str):
        payload = {
            "metadata": {"export_version": "1.0", "source": "PhiOS Phase 1"},
            "status": {},
            "field": {},
            "anchor": {},
            "capsules": {},
        }
        out = tmp_path / path.split("/")[-1]
        out.write_text(json.dumps(payload), encoding="utf-8")
        return out

    monkeypatch.setattr("phios.shell.phi_commands.export_phase1_bundle", fake_export)
    out, code = route_command(["sovereign", "export", str(output)])
    assert code == 0
    assert "Phase 1 export bundle" in out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "PhiOS Phase 1"


def test_missing_phik_produces_clean_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: None)
    with pytest.raises(PhiKernelUnavailableError):
        PhiKernelCLIAdapter().status()


def test_adapter_never_uses_shell_true(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*args, **kwargs):
        assert kwargs.get("shell") is False
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    data = PhiKernelCLIAdapter().status()
    assert data == {}
