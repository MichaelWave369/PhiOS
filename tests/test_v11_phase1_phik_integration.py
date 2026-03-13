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


def test_doctor_when_phik_missing(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.build_doctor_report", lambda *_: {"status": "missing_phik", "checks": {"phik_callable": False, "anchor_exists": False, "heart_status_exists": False, "coherence_frame_exists": False, "capsule_entries": 0}, "message": "missing"})
    out, code = route_command(["doctor", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "missing_phik"


def test_doctor_when_anchor_missing(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.build_doctor_report", lambda *_: {"status": "needs_init", "checks": {"phik_callable": True, "anchor_exists": False, "heart_status_exists": False, "coherence_frame_exists": False, "capsule_entries": 0}, "message": "init required"})
    out, code = route_command(["doctor"])
    assert code == 0
    assert "status: needs_init" in out


def test_init_successful_wrapping_behavior(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.run_init",
        lambda *_args, **_kwargs: {"ok": True, "anchor": "created"},
    )
    out, code = route_command(
        [
            "init",
            "--passphrase",
            "change-me",
            "--sovereign-name",
            "Tal-Aren-Vox",
            "--user-label",
            "Ori",
        ]
    )
    assert code == 0
    assert "Initialization Complete" in out


def test_init_existing_anchor_failure_passthrough(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.run_init",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("anchor already initialized")),
    )
    out, code = route_command(
        [
            "init",
            "--passphrase",
            "change-me",
            "--sovereign-name",
            "Tal-Aren-Vox",
            "--user-label",
            "Ori",
        ]
    )
    assert code == 1
    assert "anchor already initialized" in out


def test_pulse_once_successful_wrapping_behavior(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.run_pulse_once",
        lambda *_args, **_kwargs: {"field_action": "stabilize", "field_band": "green", "route_reason": "safe"},
    )
    out, code = route_command(["pulse", "once"])
    assert code == 0
    assert "Pulse Once" in out


def test_pulse_once_checkpoint_path(monkeypatch):
    captured = {}

    def fake_pulse(*_args, **kwargs):
        captured.update(kwargs)
        return {"field_action": "stabilize", "field_band": "green", "route_reason": "safe"}

    monkeypatch.setattr("phios.shell.phi_commands.run_pulse_once", fake_pulse)
    out, code = route_command(["pulse", "once", "--checkpoint", "./cp.json", "--passphrase", "change-me"])
    assert code == 0
    assert captured["checkpoint"] == "./cp.json"
    assert captured["passphrase"] == "change-me"


def test_json_output_contracts_for_new_commands(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.build_doctor_report", lambda *_: {"status": "ready"})
    monkeypatch.setattr("phios.shell.phi_commands.run_init", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr("phios.shell.phi_commands.run_pulse_once", lambda *_args, **_kwargs: {"ok": True})

    doc_out, doc_code = route_command(["doctor", "--json"])
    init_out, init_code = route_command([
        "init",
        "--passphrase",
        "change-me",
        "--sovereign-name",
        "Tal-Aren-Vox",
        "--user-label",
        "Ori",
        "--json",
    ])
    pulse_out, pulse_code = route_command(["pulse", "once", "--json"])

    assert doc_code == 0 and init_code == 0 and pulse_code == 0
    assert json.loads(doc_out)["status"] == "ready"
    assert json.loads(init_out)["ok"] is True
    assert json.loads(pulse_out)["ok"] is True


def test_observatory_wraps_phik_backed_data(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_observatory_report",
        lambda *_: {
            "observatory_frame": {
                "anchor_state": "verified",
                "current_field_action": "stabilize",
                "drift_band": "green",
                "capsule_continuity_count": 3,
                "C_landscape_state": "convergent",
                "observer_stability": "steady",
                "entropy_gradient_state": "contained",
                "information_gradient_state": "rich",
                "collapse_risk": "managed",
                "recognition_readiness": "high",
                "zhemawit_mode": "observatory-symbolic",
            },
            "symbolic_mapping": {"Z_Hemawit": "frame"},
        },
    )
    out, code = route_command(["observatory"])
    assert code == 0
    assert "Hemavit Observatory" in out
    assert "anchor_state: verified" in out


def test_z_map_returns_expected_mapping_table(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.zhemawit_mapping_table",
        lambda: {"C_landscape": "coherence frame space", "Z_Hemawit": "total frame"},
    )
    out, code = route_command(["z", "map", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "C_landscape" in data["symbolic_mapping"]


def test_observatory_export_writes_valid_json(monkeypatch, tmp_path):
    output = tmp_path / "obs.json"

    def fake_export(_, path: str):
        payload = {
            "metadata": {"export_version": "1.0", "source": "PhiOS Hemavit Observatory"},
            "status": {},
            "field": {},
            "observatory_frame": {"zhemawit_mode": "observatory-symbolic"},
            "symbolic_mapping": {"Z_Hemawit": "frame"},
        }
        out = tmp_path / path.split("/")[-1]
        out.write_text(json.dumps(payload), encoding="utf-8")
        return out

    monkeypatch.setattr("phios.shell.phi_commands.export_observatory_bundle", fake_export)
    out, code = route_command(["observatory", "export", str(output)])
    assert code == 0
    assert "observatory bundle" in out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "PhiOS Hemavit Observatory"


def test_observatory_missing_phik_fails_cleanly(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_observatory_report",
        lambda *_: (_ for _ in ()).throw(RuntimeError("PhiKernel CLI `phik` was not found")),
    )
    out, code = route_command(["observatory"])
    assert code == 1
    assert "phik" in out.lower()


def test_mind_wraps_phik_backed_data(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_psi_mind_report",
        lambda *_: {
            "mind_observatory_frame": {
                "anchor_state": "verified",
                "current_field_action": "stabilize",
                "drift_band": "green",
                "capsule_continuity_count": 2,
                "psi_mind_state": "coherent",
                "observer_coupling": "aligned",
                "entropy_load": "light",
                "information_density": "rich",
                "kernel_resonance": "strong",
                "overlap_strength": "emerging",
                "collapse_risk": "managed",
                "recognition_readiness": "high",
                "mind_mode": "psi_mind_observatory",
            }
        },
    )
    out, code = route_command(["mind"])
    assert code == 0
    assert "Ψ_mind Observatory" in out
    assert "psi_mind_state: coherent" in out


def test_mind_map_returns_expected_mapping_table(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.psi_mind_mapping_table",
        lambda: {"Ψ_mind": "state", "κC": "coherence contribution"},
    )
    out, code = route_command(["mind", "map", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "Ψ_mind" in data["symbolic_mapping"]


def test_mind_export_writes_valid_json(monkeypatch, tmp_path):
    output = tmp_path / "mind.json"

    def fake_export(_, path: str):
        payload = {
            "metadata": {"export_version": "1.0", "source": "PhiOS PsiMind Observatory"},
            "status": {},
            "field": {},
            "mind_observatory_frame": {"mind_mode": "psi_mind_observatory"},
            "symbolic_mapping": {"Ψ_mind": "state"},
        }
        out = tmp_path / path.split("/")[-1]
        out.write_text(json.dumps(payload), encoding="utf-8")
        return out

    monkeypatch.setattr("phios.shell.phi_commands.export_psi_mind_bundle", fake_export)
    out, code = route_command(["mind", "export", str(output)])
    assert code == 0
    assert "Ψ_mind observatory bundle" in out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "PhiOS PsiMind Observatory"


def test_mind_missing_phik_fails_cleanly(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_psi_mind_report",
        lambda *_: (_ for _ in ()).throw(RuntimeError("PhiKernel CLI `phik` was not found")),
    )
    out, code = route_command(["mind"])
    assert code == 1
    assert "phik" in out.lower()


def test_session_start_returns_valid_startup_report(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_session_start_report",
        lambda *_: {
            "session_state": "steady",
            "anchor_ready": "verified",
            "heart_ready": "running",
            "field_action": "maintain",
            "drift_band": "green",
            "observatory_mode": "observatory-symbolic",
            "mind_mode": "psi_mind_observatory",
            "observer_state": "grounded",
            "self_alignment": "aligned",
            "next_step": "Run: phi session checkin",
        },
    )
    out, code = route_command(["session", "start", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["anchor_ready"] == "verified"


def test_session_checkin_returns_integrated_report(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_session_checkin_report",
        lambda *_: {
            "session_state": "steady",
            "field_state": {"action": "maintain"},
            "observatory_state": {"zhemawit_mode": "observatory-symbolic"},
            "mind_state": {"mind_mode": "psi_mind_observatory"},
            "observer_state": "grounded",
            "self_alignment": "aligned",
            "information_density": "rich",
            "entropy_load": "light",
            "emergence_pressure": "steady",
            "collapse_risk": "managed",
            "recognition_readiness": "high",
            "recommended_action": "maintain",
            "recommended_prompt": "What one grounded next step should I take now?",
            "next_step": "Run: phi ask",
            "zhemawit_mode": "observatory-symbolic",
        },
    )
    out, code = route_command(["session", "checkin", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["session_state"] == "steady"


def test_session_export_writes_valid_json(monkeypatch, tmp_path):
    output = tmp_path / "session.json"

    def fake_export(_, path: str):
        payload = {
            "metadata": {"export_version": "1.0", "source": "PhiOS Session Layer"},
            "status": {},
            "coherence": {},
            "hemavit_observatory_frame": {},
            "psi_mind_observatory_frame": {},
            "session_summary": {"session_state": "steady"},
            "symbolic_session_fields": {"observer_state": "grounded"},
        }
        out = tmp_path / path.split("/")[-1]
        out.write_text(json.dumps(payload), encoding="utf-8")
        return out

    monkeypatch.setattr("phios.shell.phi_commands.export_session_bundle", fake_export)
    out, code = route_command(["session", "export", str(output)])
    assert code == 0
    assert "Session bundle written" in out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "PhiOS Session Layer"


def test_session_missing_phik_fails_cleanly(monkeypatch):
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_session_start_report",
        lambda *_: (_ for _ in ()).throw(RuntimeError("PhiKernel CLI `phik` was not found")),
    )
    out, code = route_command(["session", "start"])
    assert code == 1
    assert "phik" in out.lower()



def test_bio_add_writes_valid_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    out, code = route_command([
        "bio",
        "add",
        "--name",
        "Lion's Mane",
        "--compound",
        "Erinacine A",
        "--source",
        "mycelium",
        "--dose",
        "500",
        "--unit",
        "mg",
        "--timing",
        "morning",
        "--json",
    ])
    assert code == 0
    data = json.loads(out)
    assert data["entry"]["name"] == "Lion's Mane"


def test_bio_list_returns_stored_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    _ = route_command([
        "bio",
        "add",
        "--name",
        "Custom Stack",
        "--compound",
        "Beta-glucan",
        "--source",
        "extract",
    ])
    out, code = route_command(["bio", "list", "--json"])
    assert code == 0
    data = json.loads(out)
    assert len(data["entries"]) >= 1


def test_bio_show_returns_valid_summary_structure(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    _ = route_command([
        "bio",
        "add",
        "--name",
        "Entry A",
        "--compound",
        "Hericenone",
        "--source",
        "fruiting body",
        "--timing",
        "morning",
    ])
    out, code = route_command(["bio", "show", "--json"])
    assert code == 0
    data = json.loads(out)
    for key in [
        "bioeffector_count",
        "recent_entries",
        "dominant_source_type",
        "timing_state",
        "bioeffector_mode",
        "support_vector",
        "tracking_confidence",
        "session_correlation_readiness",
    ]:
        assert key in data


def test_bio_export_writes_valid_json(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    _ = route_command([
        "bio",
        "add",
        "--name",
        "Entry B",
        "--compound",
        "Erinacine-rich mycelium",
        "--source",
        "mycelium",
    ])
    output = tmp_path / "bio_snapshot.json"
    out, code = route_command(["bio", "export", str(output)])
    assert code == 0
    assert "Bioeffector bundle written" in out
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metadata"]["source"] == "PhiOS Bioeffector Layer"


def test_session_layer_still_passes_without_bio_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "phios.shell.phi_commands.build_session_checkin_report",
        lambda *_: {
            "session_state": "steady",
            "field_state": {"action": "maintain"},
            "observatory_state": {},
            "mind_state": {},
            "observer_state": "grounded",
            "self_alignment": "aligned",
            "information_density": "forming",
            "entropy_load": "light",
            "emergence_pressure": "steady",
            "collapse_risk": "managed",
            "recognition_readiness": "forming",
            "recommended_action": "maintain",
            "recommended_prompt": "next",
            "next_step": "Run",
            "zhemawit_mode": "observatory-symbolic",
            "bioeffector_state": "tracking-observatory",
            "support_vector": "baseline",
            "session_correlation_readiness": "forming",
        },
    )
    out, code = route_command(["session", "checkin", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["session_state"] == "steady"


def test_view_mode_sonic_generates_snapshot(monkeypatch, tmp_path):
    target = tmp_path / "bloom.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_bloom", lambda **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--output", str(target)])
    assert code == 0
    assert "Visual bloom generated" in out




def test_view_mode_sonic_live_generates_snapshot(monkeypatch, tmp_path):
    target = tmp_path / "live_bloom.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_live_bloom", lambda **_kwargs: target)
    out, code = route_command([
        "view",
        "--mode",
        "sonic",
        "--live",
        "--refresh-seconds",
        "1.5",
        "--duration",
        "5",
        "--output",
        str(target),
    ])
    assert code == 0
    assert "Live visual bloom running" in out


def test_view_mode_live_invalid_refresh_rejected():
    out, code = route_command(["view", "--mode", "sonic", "--live", "--refresh-seconds", "nope"])
    assert code == 0
    assert out.startswith("Usage: view")



def test_view_mode_snapshot_with_journal(monkeypatch, tmp_path):
    target = tmp_path / "j_bloom.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_bloom", lambda **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--journal", "--label", "focus", "--output", str(target)])
    assert code == 0
    assert "Visual bloom generated" in out


def test_view_mode_replay(monkeypatch, tmp_path):
    target = tmp_path / "replay.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_replay_bloom", lambda *_args, **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--replay", "session-1", "--output", str(target)])
    assert code == 0
    assert "Replay visual bloom generated" in out



def test_view_mode_with_preset_lens_audio(monkeypatch, tmp_path):
    target = tmp_path / "preset.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_bloom", lambda **_kwargs: target)
    out, code = route_command([
        "view", "--mode", "sonic", "--preset", "stable", "--lens", "diagnostic", "--audio-reactive", "--output", str(target)
    ])
    assert code == 0
    assert "Visual bloom generated" in out


def test_view_mode_invalid_preset_rejected():
    out, code = route_command(["view", "--mode", "sonic", "--preset", "bad"])
    assert code == 0
    assert out.startswith("Unknown preset")

def test_view_mode_rejects_unknown_mode():
    out, code = route_command(["view", "--mode", "unknown"])
    assert code == 0
    assert out.startswith("Usage: view")
