from __future__ import annotations

import subprocess

import pytest

from phios.services.visualizer import (
    VisualizerError,
    launch_bloom,
    map_kernel_to_visual_params,
    render_bloom_html,
    run_phik_json,
    write_bloom_file,
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
    assert "__PHIOS_PARAMS_JSON__" not in html
    assert '"seed":1' in html


def test_write_bloom_file_works(tmp_path):
    out = write_bloom_file("<html>ok</html>", tmp_path / "bloom.html")
    assert out.exists()
    assert "ok" in out.read_text(encoding="utf-8")


def test_browser_open_skipped_in_tests(monkeypatch, tmp_path):
    monkeypatch.setattr("phios.services.visualizer.run_phik_json", lambda args: {"C_current": 0.81} if args[0] == "field" else {"anchor_id": "x"})

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
