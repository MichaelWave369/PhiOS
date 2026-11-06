"""Guard the R5D injected-guest probe and the QEMU evidence parser contract."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "packaging/linux/tests/living_app_guest.py"
VM = ROOT / "packaging/linux/tests/qemu_install.py"


def test_both_guest_scripts_compile_and_no_prod_claims():
    guest = GUEST.read_text(encoding="utf-8")
    ast.parse(guest, filename=str(GUEST))
    spec = importlib.util.spec_from_file_location("r5d_guest_fixture_only", GUEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ast.parse(module.R5D_GUEST_APP, filename="installed-vm-test-only-app")
    # Existing installed_probe.py strips hyphens from /proc boot UUID.
    # The guest reporter MUST do the same before strict host identity checks.
    raw_uuid = "9872ab5c-11d0-4a1e-bac4-001122334455"
    assert module.r5d_normalize_boot_id("  " + raw_uuid + "\n") == (
        "9872ab5c11d04a1ebac4001122334455"
    )
    assert module.r5d_normalize_boot_id("9872ab5c11d04a1ebac4001122334455") == (
        "9872ab5c11d04a1ebac4001122334455"
    )
    assert "r5d_normalize_boot_id(" in guest

    assert "ThreadingHTTPServer" in module.R5D_GUEST_APP
    assert '"127.0.0.1"' in module.R5D_GUEST_APP
    assert "source_commit" in module.R5D_GUEST_APP
    assert "if phase == 1:" in guest
    assert "phase - 1" in guest
    assert '"test_app_process_http_healthy": True' in guest
    assert '"signed_app_artifact_installed": False' in guest
    assert '"app_platform_update_and_rollback_executed_inside_guest": False' in guest
    assert '"user_data_general_rollback_verified": False' in guest
    assert '"production_install_authority": False' in guest


def test_installed_vm_requires_real_guest_health_marker_per_boot():
    code = VM.read_text(encoding="utf-8")
    assert "living_app_guest.py" in code
    assert "r5d_guest_live_check({source!r}, {phase})" in code
    assert 'wait_for(r"PHIOS_R5D_GUEST_APP_OK:' in code
    assert 'receipt.setdefault("r5d_guest_app_boots", []).append(guest)' in code
    assert "disposable_installed_qemu_guest_test_only" in code
    assert "guest.get(\"source_commit\") != source" in code
    assert 'guest.get("test_app_process_http_healthy") is not True' in code
    assert 'guest.get("signed_app_artifact_installed") is not False' in code
    assert 'guest.get("production_install_authority") is not False' in code


def _guest_module():
    spec = importlib.util.spec_from_file_location("r5d_guest_durable", GUEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_user_state_is_synced_to_disk_and_parent_directory(tmp_path, monkeypatch):
    module = _guest_module()
    state_file = tmp_path / "user-state.json"
    real_fsync = os.fsync
    synced = []

    def observe_fsync(fd):
        st = os.fstat(fd)
        synced.append("file" if stat.S_ISREG(st.st_mode) else
                      "directory" if stat.S_ISDIR(st.st_mode) else "other")
        return real_fsync(fd)

    monkeypatch.setattr(module.r5d_os, "fsync", observe_fsync)
    body = {
        "schema": "phios.r5d_guest_user_data.v1",
        "source_commit": "a" * 40, "counter": 0, "owner_uid": 1000,
    }
    module.r5d_write_state_durable(state_file, body)
    assert json.loads(state_file.read_text(encoding="utf-8")) == body
    assert state_file.stat().st_mode & 0o777 == 0o600
    assert not state_file.with_suffix(".new").exists()
    assert synced == ["file", "directory"]
    module.r5d_sync_directory(tmp_path)
    assert synced == ["file", "directory", "directory"]


def test_embedded_guest_app_process_makes_durable_http_update(tmp_path):
    module = _guest_module()
    assert "os.fsync(handle.fileno())" in module.R5D_GUEST_APP
    assert "os.fsync(directory)" in module.R5D_GUEST_APP
    assert "os.replace(target, data_path)" in module.R5D_GUEST_APP
    state_file = tmp_path / "user-state.json"
    module.r5d_write_state_durable(state_file, {
        "schema": "phios.r5d_guest_user_data.v1",
        "source_commit": "a" * 40, "counter": 0, "owner_uid": 1000,
    })
    app_file = tmp_path / "guest.py"
    app_file.write_text(module.R5D_GUEST_APP, encoding="utf-8")
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    proc = subprocess.Popen([
        sys.executable, "-u", str(app_file), str(state_file), "a"*40, str(port),
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = "http://127.0.0.1:" + str(port)
    try:
        end = time.monotonic() + 8
        while True:
            if proc.poll() is not None:
                raise AssertionError("R5D embedded app process exited")
            try:
                with opener.open(base + "/health", timeout=1) as response:
                    assert json.loads(response.read())["status"] == "running"
                break
            except urllib.error.URLError:
                if time.monotonic() >= end:
                    raise AssertionError("R5D embedded app health timed out")
                time.sleep(0.1)
        req = urllib.request.Request(base + "/touch", data=b"", method="POST")
        with opener.open(req, timeout=2) as response:
            assert json.loads(response.read())["counter"] == 1
        assert json.loads(state_file.read_text(encoding="utf-8"))["counter"] == 1
        assert not state_file.with_suffix(".new").exists()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
