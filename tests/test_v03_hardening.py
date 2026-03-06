from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def test_shell_passthrough_uses_no_shell_true(monkeypatch):
    from phios.shell import phi_router

    calls: dict[str, object] = {}

    class DummyProc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(phi_router.subprocess, "run", fake_run)
    out, code = phi_router.run_fallback("echo hello")

    assert out == "ok"
    assert code == 0
    assert calls["kwargs"]["shell"] is False


def test_shell_passthrough_safe_with_special_chars():
    from phios.shell.phi_router import run_fallback

    out, code = run_fallback("echo 'hello;world'")
    assert code == 0
    assert "hello;world" in out


def test_sovereign_export_rejects_path_traversal(monkeypatch, tmp_path):
    from phios.core import sovereignty

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        sovereignty.export_snapshot("../escape.json")


def test_sovereign_verify_rejects_path_traversal(monkeypatch, tmp_path):
    from phios.core.sovereignty import verify_snapshot

    monkeypatch.chdir(tmp_path)
    ok, reason = verify_snapshot("../escape.json")
    assert ok is False
    assert "Path" in reason or "outside" in reason


def test_ollama_url_reads_from_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9999")
    module = importlib.import_module("phios.core.brainc_client")
    module = importlib.reload(module)
    assert module.OLLAMA_URL == "http://127.0.0.1:9999"
    assert module.get_ollama_url() == "http://127.0.0.1:9999"


def test_ollama_url_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    module = importlib.import_module("phios.core.brainc_client")
    module = importlib.reload(module)
    assert module.OLLAMA_URL == "http://localhost:11434"


def test_no_bare_excepts_in_codebase():
    for path in Path("phios").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "except:\n" not in text


def test_lt_result_uses_typeddict():
    from phios.core.lt_engine import LtResultDict

    assert hasattr(LtResultDict, "__annotations__")
    assert "lt" in LtResultDict.__annotations__


def test_snapshot_uses_typeddict():
    from phios.core.sovereignty import SovereignSnapshotDict

    assert hasattr(SovereignSnapshotDict, "__annotations__")
    assert "schema" in SovereignSnapshotDict.__annotations__

def test_version_single_source_of_truth():
    from phios import __version__

    assert __version__ == "0.3.0"
    for path in Path("phios").rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert '"0.3.0"' not in text


def test_version_matches_pyproject():
    from phios import __version__

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = {attr = "phios.__version__"}' in pyproject
    assert __version__ == "0.3.0"

def test_ollama_check_cached_within_ttl(monkeypatch):
    from phios.core import brainc_client

    brainc_client.clear_ollama_cache()
    calls = {"n": 0}

    def fake_probe(url: str, timeout: float) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(brainc_client, "_probe_ollama", fake_probe)
    assert brainc_client.ollama_available() is True
    assert brainc_client.ollama_available() is True
    assert calls["n"] == 1


def test_ollama_cache_refreshes_after_ttl(monkeypatch):
    from phios.core import brainc_client

    brainc_client.clear_ollama_cache()
    calls = {"n": 0}

    def fake_probe(url: str, timeout: float) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(brainc_client, "_probe_ollama", fake_probe)
    monkeypatch.setattr(brainc_client.time, "monotonic", lambda: 0.0)
    assert brainc_client.ollama_available() is True
    monkeypatch.setattr(brainc_client.time, "monotonic", lambda: 31.0)
    assert brainc_client.ollama_available() is True
    assert calls["n"] == 2


def test_phi_sync_status_degraded_without_tbrc(monkeypatch):
    from phios.core import phi_sync

    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    report = phi_sync.sync_status()
    assert report["available"] is False


@pytest.mark.skipif(__import__("importlib").util.find_spec("tbrc") is None, reason="TBRC not installed")
def test_phi_sync_push_creates_memory_entry():
    from phios.core import phi_sync

    report = phi_sync.sync_push()
    assert report["available"] is True


@pytest.mark.skipif(__import__("importlib").util.find_spec("tbrc") is None, reason="TBRC not installed")
def test_phi_sync_pull_returns_archive_entries():
    from phios.core import phi_sync

    report = phi_sync.sync_pull()
    assert report["available"] is True


def test_phi_sync_report_schema_correct(monkeypatch):
    from phios.core import phi_sync

    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)
    report = phi_sync.sync_both()
    assert "available" in report
    assert "action" in report
