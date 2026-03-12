from __future__ import annotations

import json
import subprocess
import time

from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import export_snapshot
from phios.shell.phi_router import route_command


def test_route_known_command():
    out, code = route_command(["version"])
    assert code == 0
    assert "PhiOS v0.1.0" in out


def test_lt_engine_range():
    val = compute_lt()["lt"]
    assert isinstance(val, float)
    assert 0.0 <= val <= 1.0


def test_coherence_speed_ci_threshold(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_coherence_report",
        lambda *_: {
            "C_current": 0.61,
            "C_star": 0.9,
            "distance_to_C_star": 0.29,
            "phi_flow": 0.5,
            "lambda_node": 0.4,
            "sigma_feedback": 0.2,
            "fragmentation_score": 0.1,
            "recommended_action": "stabilize",
        },
    )
    start = time.perf_counter()
    out, code = route_command(["coherence"])
    elapsed = time.perf_counter() - start
    assert code == 0
    assert "C_current:" in out
    assert elapsed < 0.2


def test_sovereign_export_and_verify(tmp_path):
    export_path = tmp_path / "snapshot.json"
    export_snapshot(str(export_path))
    data = json.loads(export_path.read_text(encoding="utf-8"))
    assert "sha256" in data

    out_ok, code_ok = route_command(["sovereign", "verify", str(export_path)])
    assert code_ok == 0
    assert out_ok.startswith("PASS")

    data["version"] = "tampered"
    export_path.write_text(json.dumps(data), encoding="utf-8")
    out_bad, code_bad = route_command(["sovereign", "verify", str(export_path)])
    assert code_bad == 0
    assert out_bad.startswith("FAIL")


def test_brainc_status_no_raise():
    out, code = route_command(["brainc", "status"])
    assert code == 0
    assert "brainc:" in out


def test_status_required_fields(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_status_report",
        lambda *_: {
            "anchor_verification_state": "verified",
            "heart_state": "running",
            "field_action": "maintain",
            "field_drift_band": "green",
            "capsule_count": 3,
        },
    )
    out, code = route_command(["status"])
    assert code == 0
    required = ["Anchor verification:", "Heart state:", "Field action / drift band:", "Capsules tracked:"]
    for item in required:
        assert item in out


def test_no_policy_violation_script():
    proc = subprocess.run(
        ["bash", "scripts/policy_no_telemetry_runtime.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
