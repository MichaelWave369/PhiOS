from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def _load_close_script_module():
    spec = importlib.util.spec_from_file_location("close_script", "scripts/close_github_issues.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_close_script_has_all_12_issues():
    module = _load_close_script_module()
    keys = sorted(module.ISSUE_RESOLUTIONS.keys())
    assert len(keys) == 12
    assert keys == list(range(2, 14))


def test_close_script_comments_mention_cgcardona():
    module = _load_close_script_module()
    for payload in module.ISSUE_RESOLUTIONS.values():
        assert "@cgcardona" in payload["body"]


def test_close_script_requires_github_token(monkeypatch, capsys):
    module = _load_close_script_module()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Missing GITHUB_TOKEN" in out


def test_close_script_handles_api_failure_gracefully(monkeypatch, capsys):
    module = _load_close_script_module()
    monkeypatch.setenv("GITHUB_TOKEN", "test")

    def bad_request(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(module, "_request", bad_request)
    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "network down" in out


def test_pyproject_has_homepage_url():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "Homepage = \"https://github.com/MichaelWave369/PhiOS\"" in text


def test_pyproject_has_manifesto_url():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "Manifesto = \"https://enterthefield.org/phios\"" in text


def test_phi_entrypoint_defined_in_pyproject():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'phi = "phios.shell.phi_session:main"' in text


def test_package_builds_without_error():
    if importlib.util.find_spec("build") is None:
        import pytest

        pytest.skip("build module not installed in this environment")
    proc = subprocess.run([sys.executable, "-m", "build"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_first_run_detected_when_no_config(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    assert PhiOnboard.is_first_run() is True


def test_first_run_not_triggered_when_config_exists(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / ".phi" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{}", encoding="utf-8")
    assert PhiOnboard.is_first_run() is False


def test_onboard_creates_config_file(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    assert onboard.config_file().exists()


def test_onboard_config_schema_correct(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    data = json.loads(onboard.config_file().read_text(encoding="utf-8"))
    keys = {"first_run", "installed_at", "phios_version", "onboard_lt_score", "ollama_detected", "tbrc_detected"}
    assert keys.issubset(data.keys())
    assert "hostname" not in data
    assert "username" not in data


def test_onboard_lt_score_in_config(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    data = json.loads(onboard.config_file().read_text(encoding="utf-8"))
    assert isinstance(data["onboard_lt_score"], float)


def test_onboard_never_blocks_on_missing_deps(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    monkeypatch.setattr(PhiOnboard, "_environment_report", lambda self: (_ for _ in ()).throw(RuntimeError("no deps")))
    onboard = PhiOnboard()
    onboard.run()
    assert onboard.config_file().exists()


def test_onboard_sovereignty_declaration_present():
    from phios.shell.phi_onboard import PhiOnboard

    declaration = PhiOnboard.sovereignty_declaration()
    assert "This machine is yours." in declaration
    assert "PhiOS collects no data." in declaration
    assert "No telemetry. No cloud. No compromise." in declaration


def test_welcome_art_contains_phi_symbol():
    from phios.shell.phi_onboard import PhiOnboard

    assert "φ" in PhiOnboard.welcome_art()


def test_welcome_art_contains_manifesto_tagline():
    from phios.shell.phi_onboard import PhiOnboard

    assert "We did not come here to improve the cage. We came here to end it." in PhiOnboard.welcome_art()


def test_onboard_completes_without_ollama(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.ollama_available", lambda: False)
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    assert onboard.config_file().exists()


def test_onboard_completes_without_tbrc(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("phios.shell.phi_onboard.TBRCBridge", lambda: type("B", (), {"is_available": lambda self: False})())
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    assert onboard.config_file().exists()


def test_onboard_completes_without_psutil(monkeypatch, tmp_path):
    from phios.shell.phi_onboard import PhiOnboard

    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr("phios.shell.phi_onboard.time.sleep", lambda *_: None)
    onboard = PhiOnboard()
    onboard.run()
    assert onboard.config_file().exists()
