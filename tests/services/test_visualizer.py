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
    append_or_update_journal_state,
    create_visual_bloom_session,
    launch_bloom,
    launch_live_bloom,
    launch_replay_bloom,
    load_visual_bloom_session,
    map_kernel_to_visual_params,
    render_bloom_html,
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
