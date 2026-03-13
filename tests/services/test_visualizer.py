from __future__ import annotations

import json
import subprocess

import pytest

from phios.services.visualizer import (
    VALID_LENSES,
    VALID_PRESETS,
    VisualizerError,
    apply_audio_reactive_modulation,
    apply_visual_lens,
    apply_visual_preset,
    step_visual_bloom_state,
    select_visual_bloom_state,
    export_visual_bloom_compare_report,
    compute_visual_bloom_bundle_hashes,
    compute_visual_bloom_diff_metrics,
    append_or_update_journal_state,
    add_visual_bloom_narrative_entry,
    render_visual_bloom_constellation_html,
    resolve_visual_bloom_link_ref,
    normalize_visual_bloom_tags,
    export_visual_bloom_constellation,
    add_visual_bloom_constellation_entry,
    load_visual_bloom_constellation,
    list_visual_bloom_constellations,
    create_visual_bloom_constellation,
    add_visual_bloom_narrative_link,
    search_visual_bloom_metadata,
    load_visual_bloom_pathway,
    list_visual_bloom_pathways,
    export_visual_bloom_pathway,
    create_visual_bloom_pathway,
    build_visual_bloom_bio_metadata,
    add_visual_bloom_pathway_entry,
    link_visual_bloom_pathway_steps,
    build_visual_bloom_recommendations,
    build_visual_bloom_dashboard_model,
    render_visual_bloom_dashboard_html,
    create_visual_bloom_narrative,
    export_visual_bloom_atlas,
    list_visual_bloom_narratives,
    load_visual_bloom_narrative,
    augment_visual_bloom_preview_metadata,
    build_visual_bloom_gallery_model,
    create_visual_bloom_session,
    filter_visual_bloom_gallery_entries,
    export_visual_bloom_bundle,
    launch_bloom,
    launch_compare_bloom,
    launch_live_bloom,
    launch_replay_bloom,
    list_visual_bloom_collections,
    list_visual_bloom_compare_sets,
    list_visual_bloom_sessions,
    load_visual_bloom_compare_set,
    load_visual_bloom_session,
    map_kernel_to_visual_params,
    render_bloom_html,
    write_visual_bloom_bundle_manifest,
    render_visual_bloom_gallery_html,
    resolve_visual_bloom_state_ref,
    save_visual_bloom_compare_set,
    run_phik_json,
    write_bloom_file,
    write_live_params_json,
)


def test_run_phik_json_parses_field(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["phik"], returncode=0, stdout='{"C_current":0.81}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    out = run_phik_json(["field"])
    assert out["C_current"] == 0.81


def test_run_phik_json_parses_status(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["phik"], returncode=0, stdout='{"heart_state":"running"}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    out = run_phik_json(["status"])
    assert out["heart_state"] == "running"


def test_mapping_from_telemetry_to_visual_params():
    params = map_kernel_to_visual_params(
        {"C_current": 0.9, "phi_flow": 0.7, "field_band": "Stable", "grace": 90},
        {"anchor_id": "alpha"},
    )
    assert params["coherenceC"] == 0.9
    assert params["particleCount"] == 900
    assert 1.0 <= float(params["frequency"]) <= 40.0


def test_mapping_defaults_when_missing_keys():
    params = map_kernel_to_visual_params({}, {})
    assert params["seed"] == 369369
    assert params["coherenceC"] == 0.809
    assert params["particleCount"] == 1500


def test_html_injection_replaces_placeholder_correctly():
    html = render_bloom_html({"seed": 1, "coherenceC": 0.8})
    assert "__PHIOS_INITIAL_PARAMS_JSON__" not in html
    assert 'const initialParams = {"seed":1,"coherenceC":0.8};' in html


def test_write_bloom_file_works(tmp_path):
    out = write_bloom_file("<html>ok</html>", tmp_path / "bloom.html")
    assert out.exists()
    assert "ok" in out.read_text(encoding="utf-8")


def test_browser_open_skipped_in_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "phios.services.visualizer.run_phik_json",
        lambda args: {"C_current": 0.81} if args[0] == "field" else {"anchor_id": "x"},
    )

    called = {"opened": False}

    def fake_open(_url):
        called["opened"] = True
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)
    out = launch_bloom(output_path=tmp_path / "x.html", open_browser=False)
    assert out.exists()
    assert called["opened"] is False


def test_subprocess_failure_raises_readable_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["phik"], returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(VisualizerError, match="PhiKernel command failed"):
        run_phik_json(["field"])


def test_invalid_json_raises_readable_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["phik"], returncode=0, stdout="{bad", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(VisualizerError, match="Invalid JSON"):
        run_phik_json(["field"])


def test_run_phik_json_never_uses_shell_true(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_: "/usr/bin/phik")

    def fake_run(*_args, **kwargs):
        assert kwargs.get("shell") is False
        return subprocess.CompletedProcess(args=["phik"], returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert run_phik_json(["status"]) == {}


def test_render_bloom_html_live_mode_replaces_markers():
    html = render_bloom_html({"seed": 3}, live_mode=True, refresh_seconds=1.5, params_path="live.params.json")
    assert "__PHIOS_LIVE_ENABLED__" not in html
    assert "__PHIOS_REFRESH_MS__" not in html
    assert "__PHIOS_REFRESH_SECONDS__" not in html
    assert "__PHIOS_PARAMS_PATH__" not in html
    assert "const liveMode = true;" in html
    assert 'const paramsPath = "live.params.json";' in html


def test_write_live_params_json_writes_payload(tmp_path):
    target = tmp_path / "live.params.json"
    out = write_live_params_json({"seed": 1, "timestamp": 123}, target)
    assert out == target
    assert '"timestamp": 123' in target.read_text(encoding="utf-8")


def test_create_and_load_visual_bloom_session(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 9, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "bloom.html",
        journal_dir=tmp_path,
        label="focus",
        source_command="phi view --mode sonic --journal",
    )
    loaded = load_visual_bloom_session(session_dir.name, journal_dir=tmp_path)
    assert loaded["label"] == "focus"
    assert loaded["mode"] == "snapshot"


def test_append_journal_state_writes_latest_and_state(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="live",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=1.0,
        output_path=tmp_path / "live.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(
        session_dir=session_dir,
        params={"timestamp": 123, "stateTimestamp": "2020-01-01T00:00:00Z", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "live", "driftBand": "Watch", "refreshSeconds": 1.0},
        output_html=tmp_path / "live.html",
    )
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert len(session["states"]) == 1
    assert (session_dir / "latest.params.json").exists()


def test_launch_live_bloom_updates_and_stops_at_duration(monkeypatch, tmp_path):
    target = tmp_path / "live.html"
    calls = {"n": 0}

    def fake_poll():
        calls["n"] += 1
        return ({"C_current": 0.8 + calls["n"] * 0.01}, {"anchor_id": "a"})

    monkeypatch.setattr("phios.services.visualizer.poll_kernel_state", fake_poll)
    monkeypatch.setattr("time.sleep", lambda _x: None)
    monkeypatch.setattr("webbrowser.open", lambda _u: True)

    out = launch_live_bloom(output_path=target, refresh_seconds=0.01, duration=0.02, open_browser=False)
    assert out.exists()
    assert (tmp_path / "live.params.json").exists()
    assert calls["n"] >= 2
    assert "__PHIOS_PARAMS_PATH__" not in target.read_text(encoding="utf-8")


def test_launch_live_bloom_handles_ctrl_c(monkeypatch, tmp_path):
    target = tmp_path / "stop.html"

    def fake_poll():
        raise KeyboardInterrupt

    monkeypatch.setattr("phios.services.visualizer.poll_kernel_state", fake_poll)
    monkeypatch.setattr("webbrowser.open", lambda _u: True)
    out = launch_live_bloom(output_path=target, refresh_seconds=2.0, open_browser=False)
    assert out == target


def test_launch_snapshot_with_journal(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "phios.services.visualizer.poll_kernel_state",
        lambda: ({"C_current": 0.81, "field_band": "Watch"}, {"anchor_id": "x"}),
    )
    out = launch_bloom(
        output_path=tmp_path / "snap.html",
        open_browser=False,
        journal=True,
        journal_dir=tmp_path,
        label="morning",
    )
    assert out.exists()
    sessions = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert sessions
    assert (sessions[0] / "session.json").exists()


def test_launch_live_with_journal(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_poll():
        calls["n"] += 1
        return ({"C_current": 0.82, "field_band": "Watch"}, {"anchor_id": "x"})

    monkeypatch.setattr("phios.services.visualizer.poll_kernel_state", fake_poll)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    out = launch_live_bloom(
        output_path=tmp_path / "live.html",
        refresh_seconds=0.01,
        duration=0.02,
        open_browser=False,
        journal=True,
        journal_dir=tmp_path,
        label="loop",
    )
    assert out.exists()
    sessions = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert sessions
    data = json.loads((sessions[0] / "session.json").read_text(encoding="utf-8"))
    assert data["mode"] == "live"
    assert len(data["states"]) >= 1


def test_launch_replay_bloom_from_session_id(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "orig.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(
        session_dir=session_dir,
        params={"timestamp": 1, "stateTimestamp": "2020-01-01T00:00:00Z", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"},
        output_html=tmp_path / "orig.html",
    )

    out = launch_replay_bloom(session_dir.name, output_path=tmp_path / "replay.html", open_browser=False, journal_dir=tmp_path)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert '"mode":"replay"' in html
    assert "Replay" in html



def test_apply_visual_preset_and_lens_deterministic():
    base = {"seed": 1, "coherenceC": 0.8, "particleCount": 1000, "noiseScale": 0.004}
    with_preset = apply_visual_preset(base, "stable")
    with_lens = apply_visual_lens(with_preset, "diagnostic")
    assert with_lens["preset"] == "stable"
    assert with_lens["lens"] == "diagnostic"
    assert 0.5 <= float(with_lens["trailStrength"]) <= 2.0


def test_invalid_preset_and_lens_raise():
    with pytest.raises(VisualizerError, match="Unknown preset"):
        apply_visual_preset({}, "x")
    with pytest.raises(VisualizerError, match="Unknown lens"):
        apply_visual_lens({}, "x")


def test_audio_reactive_graceful_unavailable(monkeypatch):
    monkeypatch.setattr("builtins.__import__", lambda name, *a, **k: (_ for _ in ()).throw(ImportError()) if name == "sounddevice" else __import__(name, *a, **k))
    params, status = apply_audio_reactive_modulation({"glowGain": 1.0}, True)
    assert status == "unavailable"
    assert params["audioReactive"] is False


def test_replay_backward_compatible_without_preset_lens_fields(tmp_path):
    session_dir = tmp_path / "legacy"
    session_dir.mkdir()
    session_json = session_dir / "session.json"
    session_json.write_text(json.dumps({
        "session_id": "legacy",
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
        "mode": "snapshot",
        "states": [{
            "timestamp": 1,
            "stateTimestamp": "2020-01-01T00:00:00Z",
            "seed": 1,
            "coherenceC": 0.8,
            "goldenInf": 1.618,
            "frequency": 7.83,
            "particleCount": 1500,
            "noiseScale": 0.005,
            "mode": "snapshot",
            "driftBand": "Watch"
        }]
    }), encoding="utf-8")
    out = launch_replay_bloom(str(session_json), output_path=tmp_path / "legacy_replay.html", open_browser=False)
    assert out.exists()


def test_valid_sets_exported():
    assert "stable" in VALID_PRESETS
    assert "bloom" in VALID_LENSES



def test_collection_tagging_and_browsing(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "preset": "stable", "lens": "ritual"},
        refresh_seconds=None,
        output_path=tmp_path / "orig.html",
        journal_dir=tmp_path,
        collection="morning-ritual",
    )
    append_or_update_journal_state(
        session_dir=session_dir,
        params={"timestamp": 1, "stateTimestamp": "2020-01-01T00:00:00Z", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch", "collection": "morning-ritual"},
        output_html=tmp_path / "orig.html",
    )
    cols = list_visual_bloom_collections(journal_dir=tmp_path)
    assert "morning-ritual" in cols
    sessions = list_visual_bloom_sessions(journal_dir=tmp_path, collection="morning-ritual")
    assert sessions and sessions[0]["collection"] == "morning-ritual"


def test_resolve_state_ref_by_index(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "x.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.7, "goldenInf": 1.618, "frequency": 6.0, "particleCount": 1200, "noiseScale": 0.004, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "x.html")
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 8.0, "particleCount": 1400, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "x.html")
    _session, state, idx = resolve_visual_bloom_state_ref(f"{session_dir.name}:0", journal_dir=tmp_path)
    assert idx == 0
    assert state["seed"] == 1


def test_launch_compare_bloom_renders_compare_template(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path, label="left")
    right = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003}, refresh_seconds=None, output_path=tmp_path / "r.html", journal_dir=tmp_path, label="right")
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    append_or_update_journal_state(session_dir=right, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "r.html")

    out = launch_compare_bloom(left.name, right.name, output_path=tmp_path / "compare.html", open_browser=False, journal_dir=tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "PhiOS Visual Bloom Compare" in html
    assert "__PHIOS_COMPARE_LEFT_B64__" not in html



def test_select_and_step_visual_bloom_state(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "s.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.7, "goldenInf": 1.618, "frequency": 7.0, "particleCount": 1000, "noiseScale": 0.004, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "s.html")
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 8.0, "particleCount": 1200, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "s.html")
    session = load_visual_bloom_session(session_dir.name, journal_dir=tmp_path)
    state, idx, total = select_visual_bloom_state(session, state_idx=0)
    assert idx == 0 and total == 2 and state["seed"] == 1
    state2, idx2, _ = step_visual_bloom_state(session, current_idx=0, direction=1)
    assert idx2 == 1 and state2["seed"] == 2


def test_compute_diff_metrics_and_export_report(tmp_path):
    left = {"coherenceC": 0.7, "frequency": 7.5, "particleCount": 1000, "noiseScale": 0.004, "goldenInf": 1.618, "driftBand": "Watch", "preset": "stable", "lens": "ritual", "audioStatus": "off"}
    right = {"coherenceC": 0.9, "frequency": 8.0, "particleCount": 1200, "noiseScale": 0.005, "goldenInf": 1.618, "driftBand": "Stable", "preset": "bloom", "lens": "diagnostic", "audioStatus": "enabled"}
    diff = compute_visual_bloom_diff_metrics(left, right)
    assert diff["delta_coherenceC"] == 0.2
    out = export_visual_bloom_compare_report(output_path=tmp_path / "compare.json", left=left, right=right, diff=diff)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source"] == "PhiOS Visual Bloom Compare Report"


def test_launch_compare_bloom_with_report_export(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path)
    right = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003}, refresh_seconds=None, output_path=tmp_path / "r.html", journal_dir=tmp_path)
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    append_or_update_journal_state(session_dir=right, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "r.html")
    report = tmp_path / "report.json"
    out = launch_compare_bloom(left.name, right.name, output_path=tmp_path / "compare2.html", open_browser=False, journal_dir=tmp_path, export_report_path=report)
    assert out.exists() and report.exists()


def test_compare_set_roundtrip(tmp_path):
    saved = save_visual_bloom_compare_set(
        name="morning pair",
        left_ref="s1:0",
        right_ref="s2:1",
        journal_dir=tmp_path,
        label="focus",
    )
    assert saved.exists()
    listing = list_visual_bloom_compare_sets(journal_dir=tmp_path)
    assert listing and listing[0]["name"] == "morning-pair"
    loaded = load_visual_bloom_compare_set("morning pair", journal_dir=tmp_path)
    assert loaded["left_ref"] == "s1:0"


def test_gallery_model_and_render(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "snap.html",
        journal_dir=tmp_path,
        label="gallery",
        collection="set-a",
    )
    append_or_update_journal_state(
        session_dir=session_dir,
        params={"timestamp": 1, "stateTimestamp": "2020-01-01T00:00:00Z", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"},
        output_html=tmp_path / "snap.html",
    )
    save_visual_bloom_compare_set(name="first", left_ref="a", right_ref="b", journal_dir=tmp_path)
    model = build_visual_bloom_gallery_model(journal_dir=tmp_path, collection="set-a")
    assert model["session_count"] == 1
    assert model["compare_set_count"] == 1
    html = render_visual_bloom_gallery_html(model)
    assert "Φ Visual Bloom Gallery" in html
    assert "__PHIOS_GALLERY_MODEL_JSON__" not in html


def test_export_visual_bloom_bundle_writes_manifest(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path)
    right = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003}, refresh_seconds=None, output_path=tmp_path / "r.html", journal_dir=tmp_path)
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    append_or_update_journal_state(session_dir=right, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "r.html")

    bundle_dir = export_visual_bloom_bundle(left_ref=left.name, right_ref=right.name, output_path=tmp_path / "bundle", journal_dir=tmp_path)
    manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["bundle_version"] == "v1"
    assert (bundle_dir / "compare_report.json").exists()
    assert (bundle_dir / "compare.html").exists()


def test_augment_preview_metadata_contract():
    meta = augment_visual_bloom_preview_metadata(source="session")
    assert meta["preview_type"] == "metadata-placeholder"
    assert meta["preview_status"] == "placeholder"
    assert "preview_generated_at" in meta


def test_filter_visual_bloom_gallery_entries():
    entries = [
        {"session_id": "a", "label": "morning", "collection": "x", "mode": "live", "preset": "stable", "lens": "ritual", "audio": "on", "created_at": "", "updated_at": "", "latest_timestamp": ""},
        {"session_id": "b", "label": "night", "collection": "y", "mode": "snapshot", "preset": "bloom", "lens": "diagnostic", "audio": "off", "created_at": "", "updated_at": "", "latest_timestamp": ""},
    ]
    out = filter_visual_bloom_gallery_entries(entries, search="morning", mode="live", preset="stable", audio="on")
    assert len(out) == 1 and out[0]["session_id"] == "a"


def test_bundle_hashes_and_manifest_writer(tmp_path):
    base = tmp_path / "bundle"
    base.mkdir()
    (base / "x.json").write_text('{"ok":true}', encoding="utf-8")
    hashes = compute_visual_bloom_bundle_hashes(base, {"x": "x.json", "missing": "none.txt"})
    assert len(hashes["x"]) == 64
    assert hashes["missing"] == ""
    manifest_path = write_visual_bloom_bundle_manifest(manifest_path=base / "bundle_manifest.json", payload={"manifest_version": "v2"})
    assert manifest_path.exists()
    assert '"manifest_version": "v2"' in manifest_path.read_text(encoding="utf-8")


def test_session_listing_includes_preview_metadata(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "s.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "s.html")
    sessions = list_visual_bloom_sessions(journal_dir=tmp_path)
    assert sessions and isinstance(sessions[0].get("preview"), dict)


def test_export_bundle_with_integrity_and_label(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path)
    right = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003}, refresh_seconds=None, output_path=tmp_path / "r.html", journal_dir=tmp_path)
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    append_or_update_journal_state(session_dir=right, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "r.html")
    bundle = export_visual_bloom_bundle(left_ref=left.name, right_ref=right.name, output_path=tmp_path / "bundle_int", journal_dir=tmp_path, with_integrity=True, bundle_label="demo")
    manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_mode"] == "sha256"
    assert manifest["bundle_label"] == "demo"
    assert "report" in manifest["file_hashes_sha256"]


def test_narrative_create_list_load(tmp_path):
    path = create_visual_bloom_narrative(name="morning atlas", journal_dir=tmp_path, title="Morning", summary="Focus")
    assert path.exists()
    listed = list_visual_bloom_narratives(journal_dir=tmp_path)
    assert listed and listed[0]["narrative_name"] == "morning-atlas"
    doc = load_visual_bloom_narrative("morning atlas", journal_dir=tmp_path)
    assert doc["title"] == "Morning"


def test_narrative_add_session_and_compare_entries_and_export_atlas(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path)
    right = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003}, refresh_seconds=None, output_path=tmp_path / "r.html", journal_dir=tmp_path)
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    append_or_update_journal_state(session_dir=right, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.9, "goldenInf": 1.618, "frequency": 8.5, "particleCount": 1000, "noiseScale": 0.003, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "r.html")

    create_visual_bloom_narrative(name="story", journal_dir=tmp_path)
    add_visual_bloom_narrative_entry(name="story", journal_dir=tmp_path, session_ref=f"{left.name}:0", entry_note="opening")
    add_visual_bloom_narrative_entry(name="story", journal_dir=tmp_path, compare_left=f"{left.name}:0", compare_right=f"{right.name}:0", entry_note="delta")

    out = export_visual_bloom_atlas(name="story", output_dir=tmp_path / "atlas", journal_dir=tmp_path, with_integrity=True)
    assert (out / "atlas_manifest.json").exists()
    assert (out / "atlas_index.html").exists()
    manifest = json.loads((out / "atlas_manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_mode"] == "sha256"
    assert manifest["entry_count"] == 2


def test_narrative_bad_ref_handling(tmp_path):
    create_visual_bloom_narrative(name="bad", journal_dir=tmp_path)
    add_visual_bloom_narrative_entry(name="bad", journal_dir=tmp_path, session_ref="missing")
    with pytest.raises(VisualizerError, match="Replay session file not found"):
        export_visual_bloom_atlas(name="bad", output_dir=tmp_path / "atlas_bad", journal_dir=tmp_path)


def test_normalize_visual_bloom_tags():
    assert normalize_visual_bloom_tags("Focus,focus, phase-1 ") == ["focus", "phase-1"]


def test_narrative_link_roundtrip_and_resolution(tmp_path):
    create_visual_bloom_narrative(name="a", journal_dir=tmp_path, tags="alpha")
    create_visual_bloom_narrative(name="b", journal_dir=tmp_path)
    add_visual_bloom_narrative_link(
        name="a",
        link_type="narrative",
        target_ref="b",
        journal_dir=tmp_path,
        label="related",
        tags="cross",
    )
    doc = load_visual_bloom_narrative("a", journal_dir=tmp_path)
    assert isinstance(doc.get("links"), list) and doc["links"][0]["target_ref"] == "b"
    resolved = resolve_visual_bloom_link_ref(link_type="narrative", target_ref="b", journal_dir=tmp_path)
    assert resolved["link_type"] == "narrative"


def test_constellation_create_add_list_load_and_export(tmp_path):
    left = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005}, refresh_seconds=None, output_path=tmp_path / "l.html", journal_dir=tmp_path)
    append_or_update_journal_state(session_dir=left, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "l.html")
    create_visual_bloom_narrative(name="n1", journal_dir=tmp_path)
    save_visual_bloom_compare_set(name="pair", left_ref=f"{left.name}:0", right_ref=f"{left.name}:0", journal_dir=tmp_path, tags="delta")

    create_visual_bloom_constellation(name="c1", journal_dir=tmp_path, title="Const", summary="Map", tags="field,theme")
    add_visual_bloom_constellation_entry(name="c1", journal_dir=tmp_path, narrative_ref="n1", tags="narr")
    add_visual_bloom_constellation_entry(name="c1", journal_dir=tmp_path, session_ref=f"{left.name}:0")
    add_visual_bloom_constellation_entry(name="c1", journal_dir=tmp_path, compare_set="pair")

    listed = list_visual_bloom_constellations(journal_dir=tmp_path)
    assert listed and listed[0]["constellation_name"] == "c1"
    loaded = load_visual_bloom_constellation("c1", journal_dir=tmp_path)
    assert len(loaded["entries"]) == 3

    out = export_visual_bloom_constellation(name="c1", output_dir=tmp_path / "const_out", journal_dir=tmp_path, with_integrity=True)
    assert (out / "constellation_manifest.json").exists()
    assert (out / "constellation_index.html").exists()
    manifest = json.loads((out / "constellation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_mode"] == "sha256"
    assert manifest["entry_count"] == 3


def test_render_visual_bloom_constellation_html_marker():
    html = render_visual_bloom_constellation_html({"constellation_name": "c", "entries": [], "links": []})
    assert "__PHIOS_CONSTELLATION_MODEL_JSON__" not in html


def test_constellation_bad_ref_handling(tmp_path):
    create_visual_bloom_constellation(name="bad", journal_dir=tmp_path)
    add_visual_bloom_constellation_entry(name="bad", journal_dir=tmp_path, narrative_ref="missing")
    with pytest.raises(VisualizerError, match="Narrative not found"):
        export_visual_bloom_constellation(name="bad", output_dir=tmp_path / "x", journal_dir=tmp_path)


def test_bio_metadata_schema_distinction():
    bio = build_visual_bloom_bio_metadata({"coherenceC": 0.81})
    assert bio["bio_status"] == "experimental"
    assert bio["hunter_c_status"] == "unconfirmed"
    assert abs(float(bio["bio_target"]) - 0.81055) < 1e-6


def test_pathway_create_add_list_load_and_export(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.809, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "s.html",
        journal_dir=tmp_path,
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.809, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "s.html")
    create_visual_bloom_narrative(name="npath", journal_dir=tmp_path)
    create_visual_bloom_constellation(name="cpath", journal_dir=tmp_path)

    create_visual_bloom_pathway(name="journey", journal_dir=tmp_path, title="Journey", tags="focus,alpha")
    add_visual_bloom_pathway_entry(name="journey", journal_dir=tmp_path, session_ref=f"{session_dir.name}:0", step_note="step-1")
    add_visual_bloom_pathway_entry(name="journey", journal_dir=tmp_path, narrative_ref="npath")
    add_visual_bloom_pathway_entry(name="journey", journal_dir=tmp_path, constellation_ref="cpath")

    listed = list_visual_bloom_pathways(journal_dir=tmp_path)
    assert listed and listed[0]["pathway_name"] == "journey"
    loaded = load_visual_bloom_pathway("journey", journal_dir=tmp_path)
    assert len(loaded["steps"]) == 3

    out = export_visual_bloom_pathway(name="journey", output_dir=tmp_path / "journey_out", journal_dir=tmp_path, with_integrity=True)
    assert (out / "pathway_manifest.json").exists()
    assert (out / "journey_index.html").exists()
    manifest = json.loads((out / "pathway_manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_mode"] == "sha256"


def test_pathway_bad_ref_handling(tmp_path):
    create_visual_bloom_pathway(name="badpath", journal_dir=tmp_path)
    add_visual_bloom_pathway_entry(name="badpath", journal_dir=tmp_path, session_ref="missing")
    with pytest.raises(VisualizerError, match="Replay session file not found"):
        export_visual_bloom_pathway(name="badpath", output_dir=tmp_path / "out", journal_dir=tmp_path)


def test_search_visual_bloom_metadata_filters(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.8105, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "s.html",
        journal_dir=tmp_path,
        label="focus",
        tags="coherence",
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.8105, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "s.html")
    create_visual_bloom_pathway(name="findme", journal_dir=tmp_path, tags="coherence")
    rows = search_visual_bloom_metadata(query="coherence", journal_dir=tmp_path, search_tags="coherence")
    assert rows
    only_pathways = search_visual_bloom_metadata(query="findme", journal_dir=tmp_path, search_type="pathway")
    assert only_pathways and all(r["type"] == "pathway" for r in only_pathways)



def test_pathway_branch_linking_and_dashboard(tmp_path):
    session_dir = create_visual_bloom_session(
        mode="snapshot",
        params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.809, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005},
        refresh_seconds=None,
        output_path=tmp_path / "s.html",
        journal_dir=tmp_path,
        label="seed",
        tags="branch",
    )
    append_or_update_journal_state(session_dir=session_dir, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.809, "goldenInf": 1.618, "frequency": 7.83, "particleCount": 1500, "noiseScale": 0.005, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "s.html")
    create_visual_bloom_pathway(name="journeyb", journal_dir=tmp_path)
    add_visual_bloom_pathway_entry(name="journeyb", journal_dir=tmp_path, session_ref=f"{session_dir.name}:0")
    add_visual_bloom_pathway_entry(name="journeyb", journal_dir=tmp_path, session_ref=f"{session_dir.name}:0")
    out = link_visual_bloom_pathway_steps(name="journeyb", from_step="p000", to_step="p001", journal_dir=tmp_path, branch_label="A")
    assert out.exists()
    loaded = load_visual_bloom_pathway("journeyb", journal_dir=tmp_path)
    assert loaded["branches"][0]["from_step"] == "p000"

    model = build_visual_bloom_dashboard_model(journal_dir=tmp_path)
    assert "bio_banner" in model
    html = render_visual_bloom_dashboard_html(model)
    assert "Visual Bloom Dashboard" in html


def test_recommendations_are_experimental(tmp_path):
    s1 = create_visual_bloom_session(mode="snapshot", params={"seed": 1, "driftBand": "Watch", "coherenceC": 0.80, "goldenInf": 1.618, "frequency": 7.0, "particleCount": 1000, "noiseScale": 0.004}, refresh_seconds=None, output_path=tmp_path / "1.html", journal_dir=tmp_path, label="one", tags="x")
    s2 = create_visual_bloom_session(mode="snapshot", params={"seed": 2, "driftBand": "Stable", "coherenceC": 0.81, "goldenInf": 1.618, "frequency": 8.0, "particleCount": 1100, "noiseScale": 0.004}, refresh_seconds=None, output_path=tmp_path / "2.html", journal_dir=tmp_path, label="two", tags="x")
    append_or_update_journal_state(session_dir=s1, params={"timestamp": 1, "stateTimestamp": "a", "seed": 1, "coherenceC": 0.80, "goldenInf": 1.618, "frequency": 7.0, "particleCount": 1000, "noiseScale": 0.004, "mode": "snapshot", "driftBand": "Watch"}, output_html=tmp_path / "1.html")
    append_or_update_journal_state(session_dir=s2, params={"timestamp": 2, "stateTimestamp": "b", "seed": 2, "coherenceC": 0.81, "goldenInf": 1.618, "frequency": 8.0, "particleCount": 1100, "noiseScale": 0.004, "mode": "snapshot", "driftBand": "Stable"}, output_html=tmp_path / "2.html")
    recs = build_visual_bloom_recommendations(target_ref=s1.name, journal_dir=tmp_path)
    assert recs
    assert recs[0]["recommendation_status"] == "experimental_local_similarity"
