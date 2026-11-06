"""R5D living app: actual localhost process, exact desktop update and user-data restore.

R5C had only a synthetic file-content health policy. This exercise starts
actual loopback HTTP processes for both test versions, observes a deliberately
incompatible test-only migration, uses PhiOS's real desktop rollback service,
and restores a hash-pinned snapshot of test-owned JSON.
It is NOT a signed publisher app or a production guest app upgrade.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Iterator
import urllib.error
import urllib.request

import pytest

from phios.apps.desktop_update import DesktopRollbackService, plan_desktop_rollback
from phios.apps.recovery_lab import audit_disposable_recovery
from test_app_platform_v040_update_rollback import (
    _execute_update, _rollback_request, _setup, _update_plan,
)

SERVER = Path(__file__).parent / "fixtures" / "r5d_living_server.py"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request(base: str, endpoint: str, *, post: bool = False) -> dict:
    req = urllib.request.Request(
        base + endpoint, data=b"" if post else None,
        method="POST" if post else "GET",
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=3
    ) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


@contextmanager
def running_app(asset: Path, data: Path, version: str) -> Iterator[tuple[str, dict]]:
    """One bounded, test-owned Python process serving the actual versioned payload."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-u", str(SERVER), "--asset", str(asset),
         "--data", str(data), "--port", str(port), "--expected", version],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, cwd=str(data.parent),
    )
    base = "http://127.0.0.1:" + str(port)
    try:
        deadline = time.monotonic() + 12
        while True:
            if proc.poll() is not None:
                raise AssertionError("Living fixture subprocess exited before health probe")
            try:
                health = request(base, "/health")
                break
            except (OSError, urllib.error.URLError):
                if time.monotonic() > deadline:
                    raise AssertionError("Living fixture failed HTTP health deadline")
                time.sleep(0.1)
        assert health["version"] == version
        assert health["asset_sha256"] == sha(asset.read_bytes())
        assert health["pid"] == proc.pid
        yield base, health
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def restore_snapshot(snapshot: Path, pinned_sha: str, target: Path) -> None:
    """Test-only restoration of a particular JSON file, never arbitrary user data."""
    if snapshot.is_symlink() or not snapshot.is_file() or target.is_symlink():
        raise ValueError("Test-only recovery input must be a regular non-symlink file")
    source_bytes = snapshot.read_bytes()
    if sha(source_bytes) != pinned_sha or len(source_bytes) > 16384:
        raise ValueError("Test-only backup changed after explicit snapshot review")
    payload = json.loads(source_bytes)
    if (
        type(payload) is not dict
        or set(payload) != {"schema", "counter", "note"}
        or payload["schema"] != "r5d.fixture.user_state.v1"
        or type(payload["counter"]) is not int
        or not isinstance(payload["note"], str)
    ):
        raise ValueError("Backup is not the exact supported test-only user-data format")
    temp = target.with_name(".r5d-user-state-restore.tmp")
    if temp.exists() or temp.is_symlink():
        raise ValueError("Refusing unexpected test-only recovery destination")
    try:
        temp.write_bytes(source_bytes)
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()


def test_real_process_upgrade_migration_rollback_and_specific_user_data_restore(
    tmp_path: Path,
) -> None:
    state = _setup(tmp_path)
    plan = _update_plan(state)
    entry = Path(plan.desktop_entry_path)
    original_entry = entry.read_bytes()
    data = tmp_path / "user-data" / "profile.json"
    data.parent.mkdir(mode=0o700)
    data.write_text(json.dumps({
        "schema": "r5d.fixture.user_state.v1",
        "counter": 9,
        "note": "GMED Union real fixture data",
    }, sort_keys=True)+"\n", encoding="utf-8")
    v1asset = state["v1"]["install_path"] / "payload/dist/index.html"
    v2asset = state["v2"]["install_path"] / "payload/dist/index.html"

    # Actually execute a process and issue HTTP requests for v1 content + state.
    with running_app(v1asset, data, "version-one") as (base, first_health):
        assert first_health["state_schema"] == "r5d.fixture.user_state.v1"
        assert request(base, "/data")["counter"] == 9
        assert request(base, "/record", post=True)["counter"] == 10
    before_update = data.read_bytes()
    snapshot = tmp_path / "snapshots" / "profile-v1.json"
    snapshot.parent.mkdir(mode=0o700)
    snapshot.write_bytes(before_update)
    pinned_snapshot = sha(before_update)

    # This is the real governed desktop update; no unreviewed install command.
    _, updated = _execute_update(state)
    assert updated.receipt.status == "updated"
    assert entry.read_bytes() != original_entry

    # Actually start v2 and mutate the SAME external data into an incompatible
    # test schema, then detect a failed post-update compatibility policy.
    with running_app(v2asset, data, "version-two") as (base, next_health):
        assert next_health["state_schema"] == "r5d.fixture.user_state.v1"
        changed = request(base, "/migrate", post=True)
        assert changed["schema"] == "r5d.fixture.user_state.v2"
        assert changed["counter"] == 110
        assert request(base, "/data") == changed
    migrated_digest = sha(data.read_bytes())
    assert migrated_digest != pinned_snapshot
    expected_previous_schema = "r5d.fixture.user_state.v1"
    assert changed["schema"] != expected_previous_schema  # Actual probe mismatch

    # Exact existing PhiOS rollback approvals and service, independently from
    # the test's file restore. Nothing runs unattended on a production system.
    rollback = plan_desktop_rollback(
        updated.receipt.to_dict(),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )
    assert rollback.rollback_authority is False
    result = DesktopRollbackService().execute(
        _rollback_request(rollback, updated.receipt),
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    assert result.receipt.status == "rolled_back"
    assert entry.read_bytes() == original_entry

    # Test-only explicit user-data snapshot restore, pinned to exact old bytes.
    restore_snapshot(snapshot, pinned_snapshot, data)
    restored_digest = sha(data.read_bytes())
    assert restored_digest == pinned_snapshot

    # A NEW ACTUAL PROCESS is running v1 and reading the recovered data.
    with running_app(v1asset, data, "version-one") as (base, recovered_health):
        assert recovered_health["state_schema"] == expected_previous_schema
        recovered_data = request(base, "/data")
        assert recovered_data == json.loads(before_update)
        assert request(base, "/record", post=True)["counter"] == 11

    filesystem = audit_disposable_recovery(
        update_receipt_value=updated.receipt.to_dict(),
        rollback_receipt_value=result.receipt.to_dict(),
        update_receipt_path=Path(updated.receipt_path),
        rollback_receipt_path=Path(result.receipt_path),
        desktop_entry_path=entry,
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        install_root=state["v1"]["install_root"],
        receipt_root=state["receipt_root"],
        observed_failure_mode="simulated_post_update_health_probe_failure",
    )
    assert filesystem["status"] == "DISPOSABLE_FILESYSTEM_RECOVERY_OBSERVED"
    report = {
        "schema": "phios.r5d_live_application_rehearsal.v0.1",
        "status": "RUNNER_REAL_HTTP_PROCESS_AND_FIXTURE_DATA_RESTORED",
        "scope": "disposable_linux_ci_runner_test_only",
        "app_id": updated.receipt.app_id,
        "original_version": updated.receipt.from_version,
        "candidate_version": updated.receipt.to_version,
        "update_receipt_sha256": updated.receipt.sha256(),
        "rollback_receipt_sha256": result.receipt.sha256(),
        "r5c_disposable_recovery_audit_sha256": filesystem["report_sha256"],
        "before_update_user_data_sha256": pinned_snapshot,
        "migrated_user_data_sha256": migrated_digest,
        "restored_user_data_sha256": restored_digest,
        "v1_process_before_update_healthy": True,
        "v2_process_started_and_migration_observed": True,
        "incompatible_fixture_schema_detected": True,
        "v1_process_after_rollback_healthy": True,
        "specific_fixture_data_restored_from_pinned_snapshot": True,
        "publisher_identity_verified": False,
        "production_signed_artifact_installed": False,
        "installed_vm_app_platform_rollback_verified": False,
        "generic_user_data_rollback_verified": False,
        "production_install_authority": False,
    }
    report["report_sha256"] = sha(json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8"))
    output = os.environ.get("PHIOS_R5D_EVIDENCE_DIR")
    if output:
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        (root / "runner-living-app-recovery.json").write_text(
            json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8"
        )


def test_tampered_user_data_snapshot_is_refused_without_mutating_active_data(
    tmp_path: Path,
) -> None:
    original = tmp_path / "snapshot.json"
    target = tmp_path / "state.json"
    original.write_text(json.dumps({
        "schema": "r5d.fixture.user_state.v1",
        "counter": 15, "note": "before upgrade",
    }), encoding="utf-8")
    target.write_text('{"schema":"r5d.fixture.user_state.v2","counter":999}', encoding="utf-8")
    protected = target.read_bytes()
    pinned = sha(original.read_bytes())
    original.write_text(original.read_text(encoding="utf-8")+" ", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after explicit"):
        restore_snapshot(original, pinned, target)
    assert target.read_bytes() == protected
    original.unlink()
    original.symlink_to(tmp_path/"missing-snapshot")
    with pytest.raises(ValueError, match="non-symlink"):
        restore_snapshot(original, pinned, target)
    assert target.read_bytes() == protected
