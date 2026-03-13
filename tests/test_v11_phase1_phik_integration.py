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



def test_view_mode_browse_collections(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_collections", lambda **_kwargs: ["morning", "night"])
    out, code = route_command(["view", "--browse-collections"])
    assert code == 0
    assert "morning" in out


def test_view_mode_browse_collection(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_sessions", lambda **_kwargs: [{"session_id": "s1", "collection": "morning"}])
    out, code = route_command(["view", "--browse-collection", "morning"])
    assert code == 0
    assert "s1" in out


def test_view_mode_compare(monkeypatch, tmp_path):
    target = tmp_path / "compare.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_compare_bloom", lambda *_args, **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--compare", "a", "b", "--output", str(target)])
    assert code == 0
    assert "Compare visual bloom generated" in out



def test_view_mode_replay_state_idx(monkeypatch, tmp_path):
    target = tmp_path / "replay_state.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_replay_bloom", lambda *_args, **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--replay", "session-1", "--state-idx", "2", "--output", str(target)])
    assert code == 0
    assert "Replay visual bloom generated" in out


def test_view_mode_compare_export_report(monkeypatch, tmp_path):
    target = tmp_path / "compare_export.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_compare_bloom", lambda *_args, **_kwargs: target)
    out, code = route_command(["view", "--mode", "sonic", "--compare", "a:0", "b:1", "--export-report", str(tmp_path / "rep.json"), "--output", str(target)])
    assert code == 0
    assert "Compare visual bloom generated" in out


def test_view_mode_invalid_state_idx_rejected():
    out, code = route_command(["view", "--mode", "sonic", "--replay", "session-1", "--state-idx", "x"])
    assert code == 0
    assert out.startswith("Usage: view")

def test_view_mode_rejects_unknown_mode():
    out, code = route_command(["view", "--mode", "unknown"])
    assert code == 0
    assert out.startswith("Usage: view")


def test_view_mode_gallery(monkeypatch, tmp_path):
    target = tmp_path / "gallery.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_visual_bloom_gallery", lambda **_kwargs: target)
    out, code = route_command(["view", "--gallery", "--collection", "morning", "--output", str(target)])
    assert code == 0
    assert "gallery generated" in out


def test_view_mode_browse_compares(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_compare_sets", lambda **_kwargs: [{"name": "a_b"}])
    out, code = route_command(["view", "--browse-compares"])
    assert code == 0
    assert "a_b" in out


def test_view_mode_load_compare_and_save(monkeypatch, tmp_path):
    target = tmp_path / "compare.html"
    monkeypatch.setattr(
        "phios.shell.phi_commands.load_visual_bloom_compare_set",
        lambda *_args, **_kwargs: {"left_ref": "left:0", "right_ref": "right:1"},
    )
    monkeypatch.setattr("phios.shell.phi_commands.launch_compare_bloom", lambda *_args, **_kwargs: target)
    saved = {"called": False}

    def fake_save(**_kwargs):
        saved["called"] = True
        return tmp_path / "saved.json"

    monkeypatch.setattr("phios.shell.phi_commands.save_visual_bloom_compare_set", fake_save)
    out, code = route_command(["view", "--mode", "sonic", "--load-compare", "focus", "--save-compare", "focus-pair"])
    assert code == 0
    assert "Compare visual bloom generated" in out
    assert saved["called"] is True


def test_view_mode_compare_export_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_bundle", lambda **_kwargs: bundle)
    out, code = route_command(["view", "--mode", "sonic", "--compare", "a", "b", "--export-bundle", str(bundle)])
    assert code == 0
    assert "bundle exported" in out


def test_view_mode_gallery_filters(monkeypatch, tmp_path):
    target = tmp_path / "gallery_f.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_visual_bloom_gallery", lambda **_kwargs: target)
    out, code = route_command([
        "view", "--gallery", "--search", "morning", "--filter-mode", "live", "--filter-preset", "stable", "--filter-lens", "ritual", "--filter-audio", "on", "--filter-label", "focus", "--filter-session", "abc"
    ])
    assert code == 0
    assert "gallery generated" in out


def test_view_mode_compare_export_bundle_with_integrity(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle2"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_bundle", lambda **_kwargs: bundle)
    out, code = route_command([
        "view", "--mode", "sonic", "--compare", "a", "b", "--export-bundle", str(bundle), "--with-integrity", "--bundle-label", "nightly"
    ])
    assert code == 0
    assert "bundle exported" in out


def test_view_mode_create_browse_load_narrative(monkeypatch, tmp_path):
    npath = tmp_path / "n.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_narrative", lambda **_kwargs: npath)
    out, code = route_command(["view", "--create-narrative", "story", "--narrative-title", "Story", "--narrative-summary", "Summary"])
    assert code == 0
    assert "narrative created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_narratives", lambda **_kwargs: [{"narrative_name": "story"}])
    out, code = route_command(["view", "--browse-narratives"])
    assert code == 0
    assert "story" in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_narrative", lambda *_args, **_kwargs: {"narrative_name": "story", "entries": []})
    out, code = route_command(["view", "--load-narrative", "story"])
    assert code == 0
    assert "narrative_name" in out


def test_view_mode_add_to_narrative(monkeypatch, tmp_path):
    updated = tmp_path / "u.json"
    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_narrative_entry", lambda **_kwargs: updated)
    out, code = route_command(["view", "--add-to-narrative", "story", "--session", "s1:0", "--entry-note", "hello"])
    assert code == 0
    assert "narrative updated" in out


def test_view_mode_export_atlas(monkeypatch, tmp_path):
    atlas = tmp_path / "atlas"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_atlas", lambda **_kwargs: atlas)
    out, code = route_command(["view", "--export-atlas", "story", str(atlas), "--with-integrity"])
    assert code == 0
    assert "atlas exported" in out


def test_view_mode_constellation_crud_and_export(monkeypatch, tmp_path):
    cpath = tmp_path / "const.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_constellation", lambda **_kwargs: cpath)
    out, code = route_command(["view", "--create-constellation", "sky", "--constellation-title", "Sky", "--constellation-summary", "Map", "--tags", "a,b"])
    assert code == 0
    assert "constellation created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_constellations", lambda **_kwargs: [{"constellation_name": "sky"}])
    out, code = route_command(["view", "--browse-constellations"])
    assert code == 0
    assert "sky" in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_constellation", lambda *_args, **_kwargs: {"constellation_name": "sky", "entries": []})
    out, code = route_command(["view", "--load-constellation", "sky"])
    assert code == 0
    assert "constellation_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_constellation_entry", lambda **_kwargs: cpath)
    out, code = route_command(["view", "--add-to-constellation", "sky", "--narrative", "n1", "--entry-note", "x", "--tags", "t1"])
    assert code == 0
    assert "constellation updated" in out

    out_dir = tmp_path / "const_out"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_constellation", lambda **_kwargs: out_dir)
    out, code = route_command(["view", "--export-constellation", "sky", str(out_dir), "--with-integrity", "--tags", "alpha"])
    assert code == 0
    assert "constellation exported" in out


def test_view_mode_link_narrative(monkeypatch, tmp_path):
    np = tmp_path / "n.json"
    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_narrative_link", lambda **_kwargs: np)
    out, code = route_command(["view", "--link-narrative", "story", "--link-type", "narrative", "--target-ref", "story2", "--entry-note", "rel", "--tags", "cross"])
    assert code == 0
    assert "narrative link added" in out


def test_view_mode_pathway_crud_search_and_export(monkeypatch, tmp_path):
    ppath = tmp_path / "p.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_pathway", lambda **_kwargs: ppath)
    out, code = route_command(["view", "--create-pathway", "journey", "--pathway-title", "Journey", "--pathway-summary", "Summary", "--tags", "focus"])
    assert code == 0
    assert "pathway created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_pathways", lambda **_kwargs: [{"pathway_name": "journey"}])
    out, code = route_command(["view", "--browse-pathways"])
    assert code == 0
    assert "journey" in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_pathway", lambda *_args, **_kwargs: {"pathway_name": "journey", "steps": []})
    out, code = route_command(["view", "--load-pathway", "journey"])
    assert code == 0
    assert "pathway_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_pathway_entry", lambda **_kwargs: ppath)
    out, code = route_command(["view", "--add-to-pathway", "journey", "--session", "s1:0", "--step-note", "note", "--tags", "a"])
    assert code == 0
    assert "pathway updated" in out

    monkeypatch.setattr("phios.shell.phi_commands.search_visual_bloom_metadata", lambda **_kwargs: [{"type": "pathway", "id": "journey"}])
    out, code = route_command(["view", "--search", "journey", "--search-type", "pathway", "--search-tags", "a", "--search-bio", "experimental"])
    assert code == 0
    assert "journey" in out

    out_dir = tmp_path / "pout"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_pathway", lambda **_kwargs: out_dir)
    out, code = route_command(["view", "--export-pathway", "journey", str(out_dir), "--with-integrity", "--tags", "focus"])
    assert code == 0
    assert "pathway exported" in out



def test_view_mode_phase13_branching_dashboard_and_recommendations(monkeypatch, tmp_path):
    ppath = tmp_path / "journey.json"
    ppath.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("phios.shell.phi_commands.link_visual_bloom_pathway_steps", lambda **_kwargs: ppath)
    out, code = route_command(["view", "--link-pathway-step", "journey", "--from-step", "p000", "--to-step", "p001", "--branch-label", "A"])
    assert code == 0
    assert "pathway linked" in out

    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_recommendations", lambda **_kwargs: [{"id": "s2"}])
    out, code = route_command(["view", "--recommend-for", "s1"])
    assert code == 0
    assert '"count": 1' in out

    dpath = tmp_path / "dashboard.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_visual_bloom_dashboard", lambda **_kwargs: dpath)
    out, code = route_command(["view", "--dashboard", "--output", str(dpath)])
    assert code == 0
    assert "dashboard generated" in out



def test_view_mode_phase14_recommend_strategy_and_benchmark(monkeypatch):
    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_recommendations", lambda **_kwargs: [{"id": "x", "strategy": "baseline_cosine"}])
    out, code = route_command(["view", "--recommend-for", "s1", "--recommend-strategy", "baseline_cosine"])
    assert code == 0
    assert '"strategy": "baseline_cosine"' in out

    monkeypatch.setattr("phios.shell.phi_commands.benchmark_visual_bloom_recommendations", lambda **_kwargs: {"status": "experimental_exploratory_benchmark", "results": []})
    out, code = route_command(["view", "--benchmark-recommendations", "--recommend-strategy", "golden_rbf,baseline_rbf"])
    assert code == 0
    assert "experimental_exploratory_benchmark" in out



def test_view_mode_phase14_atlas_flags(monkeypatch, tmp_path):
    apath = tmp_path / "atlas.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_visual_bloom_atlas", lambda **_kwargs: apath)
    out, code = route_command(["view", "--atlas", "--atlas-target", "bio_band", "--atlas-max-l1-radius", "2", "--atlas-heat-mode", "bio_band_proximity", "--output", str(apath)])
    assert code == 0
    assert "atlas generated" in out



def test_view_mode_phase15_sector_and_insight_pack_flags(monkeypatch, tmp_path):
    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_sectors", lambda _fam=None: [{"sector_id": "geometry", "family": "HG"}])
    out, code = route_command(["view", "--list-sectors", "--sector-family", "HG"])
    assert code == 0
    assert '"count": 1' in out

    pdir = tmp_path / "pack"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_insight_pack", lambda **_kwargs: pdir)
    out, code = route_command(["view", "--export-insight-pack", "pathway1", str(pdir), "--insight-pack-title", "Pack", "--insight-pack-include-atlas", "--insight-pack-heat-mode", "geometry_balance"])
    assert code == 0
    assert "insight pack exported" in out



def test_view_mode_phase16_branch_replay_route_compare_and_diagnostics(monkeypatch, tmp_path):
    bpath = tmp_path / "branch.html"
    monkeypatch.setattr("phios.shell.phi_commands.launch_visual_bloom_branch_replay", lambda **_kwargs: bpath)
    out, code = route_command(["view", "--branch-replay", "p1", "--output", str(bpath)])
    assert code == 0
    assert "branch replay generated" in out

    rdir = tmp_path / "routecmp"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_route_compare_bundle", lambda **_kwargs: rdir)
    out, code = route_command(["view", "--export-route-compare", "s1:0", str(rdir), "--route-compare-title", "R", "--route-compare-heat-mode", "geometry_balance", "--route-compare-include-sector-overlays"])
    assert code == 0
    assert "route compare exported" in out

    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_strategy_diagnostics", lambda **_kwargs: {"status": "experimental_strategy_diagnostics"})
    out, code = route_command(["view", "--show-strategy-diagnostics", "s1"])
    assert code == 0
    assert "experimental_strategy_diagnostics" in out



def test_view_mode_phase17_storyboard_flags(monkeypatch, tmp_path):
    sp = tmp_path / "sb.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_storyboard", lambda **_kwargs: sp)
    out, code = route_command(["view", "--create-storyboard", "sb", "--storyboard-title", "S"])
    assert code == 0
    assert "storyboard created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_storyboards", lambda **_kwargs: [{"storyboard_name": "sb"}])
    out, code = route_command(["view", "--browse-storyboards"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_storyboard", lambda *_args, **_kwargs: {"storyboard_name": "sb", "sections": []})
    out, code = route_command(["view", "--load-storyboard", "sb"])
    assert code == 0
    assert "storyboard_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_storyboard_section", lambda **_kwargs: sp)
    out, code = route_command(["view", "--add-to-storyboard", "sb", "--section-type", "insight_pack", "--artifact-ref", "/tmp/p"])
    assert code == 0
    assert "storyboard updated" in out

    outdir = tmp_path / "story"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_storyboard", lambda **_kwargs: outdir)
    out, code = route_command(["view", "--export-storyboard", "sb", str(outdir), "--storyboard-filter-tags", "focus", "--storyboard-filter-sector", "geometry", "--storyboard-filter-type", "insight_pack"])
    assert code == 0
    assert "storyboard exported" in out


def test_view_mode_phase18_gallery_and_longitudinal_flags(monkeypatch, tmp_path):
    gpath = tmp_path / "atlas_gallery.html"
    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_atlas_gallery_model", lambda **_kwargs: {"entries": [], "framing": {"c_star_theoretical": 0.809, "bio_target": 0.81055, "bio_status": "experimental", "hunter_c_status": "unconfirmed"}, "filters": {}, "sector_snapshot": {}})
    monkeypatch.setattr("phios.shell.phi_commands.render_visual_bloom_atlas_gallery_html", lambda _model: "<html>gallery</html>")
    monkeypatch.setattr("phios.shell.phi_commands.write_bloom_file", lambda _html, _target: gpath)
    out, code = route_command(["view", "--atlas-gallery"])
    assert code == 0
    assert "atlas gallery generated" in out

    outdir = tmp_path / "longitudinal"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_longitudinal_summary", lambda **_kwargs: outdir)
    out, code = route_command(["view", "--export-longitudinal-summary", str(outdir), "--longitudinal-filter-target", "theoretical"])
    assert code == 0
    assert "longitudinal summary exported" in out


def test_view_mode_phase19_dossier_flags(monkeypatch, tmp_path):
    dpath = tmp_path / "dossier.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_dossier", lambda **_kwargs: dpath)
    out, code = route_command(["view", "--create-dossier", "d1", "--dossier-title", "D"])
    assert code == 0
    assert "dossier created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_dossiers", lambda **_kwargs: [{"dossier_name": "d1"}])
    out, code = route_command(["view", "--browse-dossiers"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_dossier", lambda *_args, **_kwargs: {"dossier_name": "d1", "sections": []})
    out, code = route_command(["view", "--load-dossier", "d1"])
    assert code == 0
    assert "dossier_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_dossier_section", lambda **_kwargs: dpath)
    out, code = route_command(["view", "--add-to-dossier", "d1", "--section-type", "storyboard", "--artifact-ref", "/tmp/sb"])
    assert code == 0
    assert "dossier updated" in out

    outdir = tmp_path / "dossier"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_dossier", lambda **_kwargs: outdir)
    out, code = route_command(["view", "--export-dossier", "d1", str(outdir), "--dossier-filter-type", "storyboard", "--dossier-filter-target", "theoretical"])
    assert code == 0
    assert "dossier exported" in out


def test_view_mode_phase20_field_library_flags(monkeypatch, tmp_path):
    fpath = tmp_path / "field_library.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_field_library", lambda **_kwargs: fpath)
    out, code = route_command(["view", "--create-field-library", "fl1", "--field-library-title", "F"])
    assert code == 0
    assert "field library created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_field_libraries", lambda **_kwargs: [{"library_name": "fl1"}])
    out, code = route_command(["view", "--browse-field-libraries"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_field_library", lambda *_args, **_kwargs: {"library_name": "fl1", "collections": []})
    out, code = route_command(["view", "--load-field-library", "fl1"])
    assert code == 0
    assert "library_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_field_library_entry", lambda **_kwargs: fpath)
    out, code = route_command(["view", "--add-to-field-library", "fl1", "--section-type", "dossier", "--artifact-ref", "/tmp/d"])
    assert code == 0
    assert "field library updated" in out

    outdir = tmp_path / "field_library"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_field_library", lambda **_kwargs: outdir)
    out, code = route_command(["view", "--export-field-library", "fl1", str(outdir), "--field-library-filter-type", "dossier", "--field-library-filter-target", "theoretical"])
    assert code == 0
    assert "field library exported" in out


def test_view_mode_phase21_shelf_and_catalog_flags(monkeypatch, tmp_path):
    spath = tmp_path / "shelf.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_shelf", lambda **_kwargs: spath)
    out, code = route_command(["view", "--create-shelf", "s1", "--shelf-title", "S"])
    assert code == 0
    assert "shelf created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_shelves", lambda **_kwargs: [{"shelf_name": "s1"}])
    out, code = route_command(["view", "--browse-shelves"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_shelf", lambda *_args, **_kwargs: {"shelf_name": "s1", "items": []})
    out, code = route_command(["view", "--load-shelf", "s1"])
    assert code == 0
    assert "shelf_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_shelf_item", lambda **_kwargs: spath)
    out, code = route_command(["view", "--add-to-shelf", "s1", "--section-type", "dossier", "--artifact-ref", "/tmp/d"])
    assert code == 0
    assert "shelf updated" in out

    outdir = tmp_path / "shelf"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_shelf", lambda **_kwargs: outdir)
    out, code = route_command(["view", "--export-shelf", "s1", str(outdir), "--shelf-filter-type", "dossier"])
    assert code == 0
    assert "shelf exported" in out

    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_catalog_model", lambda **_kwargs: {"generated_at": "", "entry_count": 1, "entries": [{"artifact_type": "dossier", "title": "D"}]})
    monkeypatch.setattr("phios.shell.phi_commands.filter_visual_bloom_catalog_entries", lambda **_kwargs: [{"artifact_type": "dossier", "title": "D"}])
    monkeypatch.setattr("phios.shell.phi_commands.group_visual_bloom_catalog_entries", lambda **_kwargs: {"dossier": [{"title": "D"}]})
    out, code = route_command(["view", "--browse-catalog", "--catalog-group-by", "artifact_type"])
    assert code == 0
    assert "grouped_entries" in out


def test_view_mode_phase22_reading_room_and_collection_map_flags(monkeypatch, tmp_path):
    rr = tmp_path / "rr.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_reading_room", lambda **_kwargs: rr)
    out, code = route_command(["view", "--create-reading-room", "rr1", "--reading-room-title", "Room"])
    assert code == 0
    assert "reading room created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_reading_rooms", lambda **_kwargs: [{"reading_room_name": "rr1"}])
    out, code = route_command(["view", "--browse-reading-rooms"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_reading_room", lambda *_args, **_kwargs: {"reading_room_name": "rr1", "sections": []})
    out, code = route_command(["view", "--load-reading-room", "rr1"])
    assert code == 0
    assert "reading_room_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_reading_room_section", lambda **_kwargs: rr)
    out, code = route_command(["view", "--add-to-reading-room", "rr1", "--section-type", "shelf", "--artifact-ref", "/tmp/s"])
    assert code == 0
    assert "reading room updated" in out

    rr_out = tmp_path / "rr"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_reading_room", lambda **_kwargs: rr_out)
    out, code = route_command(["view", "--export-reading-room", "rr1", str(rr_out)])
    assert code == 0
    assert "reading room exported" in out

    mp = tmp_path / "map.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_collection_map", lambda **_kwargs: mp)
    out, code = route_command(["view", "--create-collection-map", "m1", "--collection-map-tags", "focus"])
    assert code == 0
    assert "collection map created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_collection_maps", lambda **_kwargs: [{"collection_map_name": "m1"}])
    out, code = route_command(["view", "--browse-collection-maps"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_collection_map_model", lambda **_kwargs: {"collection_map_name": "m1", "nodes": [], "edges": []})
    out, code = route_command(["view", "--load-collection-map", "m1"])
    assert code == 0
    assert "collection_map_name" in out

    map_out = tmp_path / "map"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_collection_map", lambda **_kwargs: map_out)
    out, code = route_command(["view", "--export-collection-map", "m1", str(map_out)])
    assert code == 0
    assert "collection map exported" in out


def test_view_mode_phase23_study_hall_and_thematic_pathway_flags(monkeypatch, tmp_path):
    sh = tmp_path / "sh.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_study_hall", lambda **_kwargs: sh)
    out, code = route_command(["view", "--create-study-hall", "sh1", "--study-hall-title", "Hall"])
    assert code == 0
    assert "study hall created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_study_halls", lambda **_kwargs: [{"study_hall_name": "sh1"}])
    out, code = route_command(["view", "--browse-study-halls"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.load_visual_bloom_study_hall", lambda *_args, **_kwargs: {"study_hall_name": "sh1", "modules": []})
    out, code = route_command(["view", "--load-study-hall", "sh1"])
    assert code == 0
    assert "study_hall_name" in out

    monkeypatch.setattr("phios.shell.phi_commands.add_visual_bloom_study_hall_module", lambda **_kwargs: sh)
    out, code = route_command(["view", "--add-to-study-hall", "sh1", "--section-type", "reading_room", "--artifact-ref", "/tmp/rr"])
    assert code == 0
    assert "study hall updated" in out

    sh_out = tmp_path / "sh"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_study_hall", lambda **_kwargs: sh_out)
    out, code = route_command(["view", "--export-study-hall", "sh1", str(sh_out)])
    assert code == 0
    assert "study hall exported" in out

    tp = tmp_path / "tp.json"
    monkeypatch.setattr("phios.shell.phi_commands.create_visual_bloom_thematic_pathway", lambda **_kwargs: tp)
    out, code = route_command(["view", "--create-thematic-pathway", "tp1", "--thematic-pathway-tags", "focus"])
    assert code == 0
    assert "thematic pathway created" in out

    monkeypatch.setattr("phios.shell.phi_commands.list_visual_bloom_thematic_pathways", lambda **_kwargs: [{"thematic_pathway_name": "tp1"}])
    out, code = route_command(["view", "--browse-thematic-pathways"])
    assert code == 0
    assert '"count": 1' in out

    monkeypatch.setattr("phios.shell.phi_commands.build_visual_bloom_thematic_pathway_model", lambda **_kwargs: {"thematic_pathway_name": "tp1", "nodes": [], "links": []})
    out, code = route_command(["view", "--load-thematic-pathway", "tp1"])
    assert code == 0
    assert "thematic_pathway_name" in out

    tp_out = tmp_path / "tp"
    monkeypatch.setattr("phios.shell.phi_commands.export_visual_bloom_thematic_pathway", lambda **_kwargs: tp_out)
    out, code = route_command(["view", "--export-thematic-pathway", "tp1", str(tp_out)])
    assert code == 0
    assert "thematic pathway exported" in out
