from __future__ import annotations

import errno
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from phios.curiosity import CuriosityArtifact
from phios.curiosity_store import CuriosityStore
from phios.memory import MemoryOperatorRuntime, MemoryRecord, MemoryRuntimeConfig, MemoryStore
from phios.state_io import StateIntegrityError, append_jsonl, read_jsonl
from phios.state_paths import configured_state_root, memory_config_path
from phios.state_recovery import backup, restore, verify_backup


def test_concurrent_processes_preserve_exact_complete_records(tmp_path: Path) -> None:
    path = tmp_path / "private" / "ledger.jsonl"
    script = """
import sys
from pathlib import Path
from phios.state_io import append_jsonl
for index in range(15):
    append_jsonl(Path(sys.argv[1]), {"id": f"{sys.argv[2]}:{index}", "text": "α" * 8192})
"""
    children = [subprocess.Popen([sys.executable, "-c", script, str(path), str(i)])
                for i in range(4)]
    # Shared CI disks can take longer to complete mandatory fsyncs. This checks
    # exact durability/concurrency, not a 30-second storage latency promise.
    # Keep one finite deadline and reap every child even when a check fails.
    deadline = time.monotonic() + 120
    try:
        for child in children:
            assert child.wait(timeout=max(0.1, deadline - time.monotonic())) == 0
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    rows = read_jsonl(path)
    assert {row["id"] for row in rows} == {f"{i}:{j}" for i in range(4) for j in range(15)}
    assert len(rows) == 60
    assert all(row["text"] == "α" * 8192 for row in rows)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_concurrent_idempotent_publication_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    payload = {"receipt_id": "same", "effect_performed": False}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: append_jsonl(path, payload, identity_field="receipt_id"), range(32),
        ))
    assert sum(results) == 1
    assert read_jsonl(path) == [payload]
    with pytest.raises(StateIntegrityError, match="collision"):
        append_jsonl(path, {**payload, "effect_performed": True}, identity_field="receipt_id")
    assert read_jsonl(path) == [payload]


def test_partial_disk_full_write_keeps_previously_acknowledged_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "ledger.jsonl"
    append_jsonl(path, {"id": "committed"})
    before = path.read_bytes()
    original = os.write
    count = 0

    def interrupted(fd: int, data: bytes) -> int:
        nonlocal count
        count += 1
        if count == 1:
            return original(fd, data[:5])
        raise OSError(errno.ENOSPC, "test disk is full")

    monkeypatch.setattr(os, "write", interrupted)
    with pytest.raises(OSError, match="full"):
        append_jsonl(path, {"id": "not-acknowledged"})
    assert path.read_bytes() == before
    assert read_jsonl(path) == [{"id": "committed"}]


@pytest.mark.skipif(os.name != "posix", reason="SIGKILL qualification is POSIX-specific")
def test_killed_writer_leaves_a_detected_tail_and_cannot_silently_continue(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    append_jsonl(path, {"id": "committed"})
    script = """
import os, sys
from pathlib import Path
from phios.state_io import append_jsonl
original = os.write
def stop_mid_write(fd, data):
    original(fd, data[:9])
    print("PARTIAL", flush=True)
    os.read(0, 1)
    raise RuntimeError("test must kill this process")
os.write = stop_mid_write
append_jsonl(Path(sys.argv[1]), {"id": "interrupted"})
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(path)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "PARTIAL"
    finally:
        child.kill()
        child.wait(timeout=5)
    evidence = path.read_bytes()
    with pytest.raises(StateIntegrityError, match="incomplete"):
        read_jsonl(path)
    with pytest.raises(StateIntegrityError, match="incomplete"):
        append_jsonl(path, {"id": "must-not-append"})
    assert path.read_bytes() == evidence


@pytest.mark.parametrize("content", [b'{}\nBROKEN\n{}\n', b'{"id":1,"id":2}\n', b'{"v":NaN}\n'])
def test_malformed_history_is_held_instead_of_skipped(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(content)
    with pytest.raises(StateIntegrityError):
        read_jsonl(path)
    with pytest.raises(StateIntegrityError):
        append_jsonl(path, {"new": True})
    assert path.read_bytes() == content


def test_symlink_ancestors_and_hardlink_aliases_are_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises((OSError, StateIntegrityError)):
        append_jsonl(alias / "ledger.jsonl", {"id": "denied"})
    assert not (real / "ledger.jsonl").exists()
    path = real / "ledger.jsonl"
    append_jsonl(path, {"id": "original"})
    os.link(path, real / "second-link")
    with pytest.raises(StateIntegrityError, match="one link"):
        append_jsonl(path, {"id": "denied"})


def _record(revision: int) -> MemoryRecord:
    return MemoryRecord.build(
        record_id="same-record", revision=revision, source_id="operator", source_kind="human",
        provenance_refs=(), created_at="2026-09-30T00:00:00+00:00", scope_id="private",
        classification="operator", retention_policy_id="retain", expires_at=None,
        epistemic_kind="source", text=f"revision {revision}",
    )


def test_old_publication_never_publishes_a_newer_pending_revision(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    for revision in [1, 2]:
        record = _record(revision)
        store.put_pending(record, operation_id=f"op-{revision}", request_sha256=str(revision) * 64,
                          receipt_json=json.dumps({"operation": "put", "record_versions": [
                              {"record_id": record.record_id, "revision": revision},
                          ]}))
    store.mark_receipt_published("op-1")
    assert store.get("same-record") is None
    store.mark_receipt_published("op-2")
    assert store.get("same-record") == _record(2)


def test_concurrent_memory_operation_retries_commit_once(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    record = _record(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.put_pending(
            record, operation_id="same-operation", request_sha256="a" * 64, receipt_json="{}",
        ), range(24)))
    assert sum(results) == 1
    assert len(store.pending_receipts()) == 1


def test_unknown_schema_is_refused_before_any_schema_change(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE store_metadata(key TEXT PRIMARY KEY, value TEXT);"
                           "INSERT INTO store_metadata VALUES('schema_version', '999');")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="unsupported"):
        MemoryStore(path)
    assert path.read_bytes() == before


def _seed(root: Path) -> MemoryOperatorRuntime:
    runtime = MemoryOperatorRuntime(
        state_root=root / "memory",
        config=MemoryRuntimeConfig(enabled=True, principal_id="operator", scopes=("private",),
                                   classifications=("operator",), retention_policy_id="retain"),
        allowed_permissions=("memory.write", "memory.read"),
    )
    assert runtime.put(_record(1), operation_id="put-1", task_id="test-data").status == "ok"
    return runtime


def _reidentify(directory: Path, name: str) -> None:
    import hashlib
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    data = (directory / name).read_bytes()
    manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    path.write_text(json.dumps(manifest))


def test_backup_restore_preserves_data_without_replaying_authority(tmp_path: Path) -> None:
    root = tmp_path / "state"
    runtime = _seed(root)
    artifact = CuriosityArtifact.build(
        artifact_kind="question", title="Recovery", content="Can this data survive a crash?",
        created_at="2026-09-30T00:00:00+00:00", created_by="operator",
    )
    CuriosityStore(root / "curiosity").append_artifact(artifact)
    active_authority = root / "spine-v0.1/ledger/ghostwalk-authorization-decisions.jsonl"
    append_jsonl(active_authority, {"receipt_id": "historical-only", "execution_authority": True})
    (root / "credentials.json").write_text("a credential must not be included")
    saved = tmp_path / "backup"
    manifest = backup(root, saved)
    assert verify_backup(saved) == manifest
    recovered = tmp_path / "restored"
    receipt = restore(saved, recovered)
    assert receipt["authority_restored"] is False
    assert receipt["configuration_restored"] is False
    assert not (recovered / "credentials.json").exists()
    assert not (recovered / "spine-v0.1/ledger/ghostwalk-authorization-decisions.jsonl").exists()
    assert (recovered / "recovered-audit/ghostwalk-authorization-decisions.jsonl").is_file()
    store = MemoryStore(recovered / "memory/canonical.sqlite3")
    assert store.get("same-record") == runtime.store.get("same-record")
    assert CuriosityStore(recovered / "curiosity").artifacts() == [artifact]
    assert recovered.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        restore(saved, recovered)


def test_corrupt_backup_is_rejected_before_destination_creation(tmp_path: Path) -> None:
    _seed(tmp_path / "state")
    saved = tmp_path / "backup"
    backup(tmp_path / "state", saved)
    path = saved / "memory/canonical.sqlite3"
    path.write_bytes(b"corrupt")
    with pytest.raises(StateIntegrityError, match="hash"):
        restore(saved, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_rehashed_unknown_schema_is_held_without_implicit_migration(tmp_path: Path) -> None:
    _seed(tmp_path / "state")
    saved = tmp_path / "backup"
    backup(tmp_path / "state", saved)
    with sqlite3.connect(saved / "memory/canonical.sqlite3") as conn:
        conn.execute("UPDATE store_metadata SET value='999' WHERE key='schema_version'")
    _reidentify(saved, "memory/canonical.sqlite3")
    with pytest.raises(StateIntegrityError, match="unsupported"):
        restore(saved, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_logically_corrupt_canonical_data_cannot_be_read_as_a_valid_record(tmp_path: Path) -> None:
    runtime = _seed(tmp_path / "state")
    with runtime.store._connect() as conn:
        row = conn.execute("SELECT payload_json FROM records").fetchone()
        payload = json.loads(row[0])
        payload["text"] = "tampered text retaining the original hashes"
        conn.execute("UPDATE records SET payload_json=?", (json.dumps(payload),))
    with pytest.raises(StateIntegrityError, match="integrity"):
        runtime.store.get("same-record")


def test_rehashed_authority_injection_cannot_enter_active_restored_ledger(tmp_path: Path) -> None:
    _seed(tmp_path / "state")
    saved = tmp_path / "backup"
    backup(tmp_path / "state", saved)
    name = "spine-v0.1/ledger/mandala-receipts.jsonl"
    append_jsonl(saved / name, {"receipt_id": "injected", "execution_authority": True})
    _reidentify(saved, name)
    with pytest.raises(StateIntegrityError, match="only exact published memory"):
        restore(saved, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_tail_recovery_preserves_raw_evidence_and_reconciles_pending_memory(tmp_path: Path) -> None:
    root = tmp_path / "state"
    runtime = _seed(root)
    # Simulate termination after a receipt append but before marking the outbox.
    with runtime.store._connect() as conn:
        conn.execute("UPDATE receipt_outbox SET published=0")
        conn.execute("UPDATE record_heads SET published=0")
    original = runtime.ledger.path.read_bytes() + b'{"receipt_id":"interrupted'
    runtime.ledger.path.write_bytes(original)
    with pytest.raises(StateIntegrityError, match="incomplete"):
        backup(root, tmp_path / "held-backup")
    saved = tmp_path / "salvage-backup"
    manifest = backup(root, saved, preserve_incomplete_tail=True)
    assert manifest["incomplete_audit_files"] == ["audit/spine-ledger-mandala-receipts.jsonl.bin"]
    assert runtime.ledger.path.read_bytes() == original
    assert (saved / manifest["incomplete_audit_files"][0]).read_bytes() == original
    recovered = tmp_path / "restored"
    restore(saved, recovered)
    resumed = MemoryOperatorRuntime(state_root=recovered / "memory", config=runtime.config,
                                    allowed_permissions=("memory.read",))
    assert resumed.publisher.publish_pending() == 1
    assert resumed.store.get("same-record") == _record(1)
    assert len(resumed.ledger.recent()) == 1
    assert resumed.publisher.publish_pending() == 0
    assert runtime.ledger.path.read_bytes() == original


def test_packaged_and_legacy_paths_require_explicit_state_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHIOS_STATE_ROOT", raising=False)
    assert configured_state_root() == Path.home() / ".phios"
    monkeypatch.setenv("PHIOS_STATE_ROOT", "/home/operator/.local/state/phios")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/operator/.config")
    assert configured_state_root() == Path("/home/operator/.local/state/phios")
    assert memory_config_path() == Path("/home/operator/.config/phios/memory.json")
    monkeypatch.setenv("PHIOS_STATE_ROOT", "relative/path")
    with pytest.raises(ValueError, match="absolute"):
        configured_state_root()
