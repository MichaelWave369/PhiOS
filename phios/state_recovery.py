"""Verified data-only backup/restore into a fresh operator-owned state root."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from phios.memory.models import MemoryRecord
from phios.memory.publisher import _receipt_from_payload
from phios.memory.store import SCHEMA_VERSION
from phios.curiosity_store import CuriosityStore
from phios.state_io import (
    StateIntegrityError, _locked, append_jsonl, prepare_state_file, read_jsonl,
    recoverable_jsonl_prefix, sync_directory,
)
from phios.state_paths import configured_state_root

FORMAT = "phios.data-backup.v1"
CANONICAL = "memory/canonical.sqlite3"
MEMORY_LEDGER = "spine-v0.1/ledger/mandala-receipts.jsonl"
DATA_FILES = {CANONICAL, MEMORY_LEDGER, "curiosity/artifacts.jsonl", "curiosity/return-pointers.jsonl"}


def _safe_root(root: Path) -> Path:
    root = root.expanduser().absolute()
    if not root.is_dir():
        raise ValueError("an existing owned state directory is required")
    # A nonexistent child lets the shared directory walker check every ancestor.
    try:
        with _locked(root / "manifest.json", write=False):
            pass
    except FileNotFoundError:
        pass
    if os.name == "posix" and (root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022):
        raise StateIntegrityError("state root owner or write permissions are unsafe")
    return root


def _hash(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with _locked(path, write=False) as (handle, _parent):
        size = os.fstat(handle.fileno()).st_size
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def _copy(source: Path, destination: Path) -> None:
    with _locked(source, write=False) as (reader, _source_parent):
        with _locked(destination, write=True) as (writer, parent):
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                remaining = memoryview(chunk)
                while remaining:
                    count = writer.write(remaining)
                    if not count:
                        raise OSError("backup copy made no progress")
                    remaining = remaining[count:]
            os.fsync(writer.fileno())
            if parent is not None:
                os.fsync(parent)


def _database(path: Path) -> list[tuple[dict[str, Any], bool]]:
    # Validate both SQLite structural integrity and the domain's content hashes.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        version = conn.execute("SELECT value FROM store_metadata WHERE key='schema_version'").fetchone()
        if version is None or version[0] != str(SCHEMA_VERSION):
            raise StateIntegrityError("unsupported canonical memory schema; no implicit migration")
        if [row[0] for row in conn.execute("PRAGMA integrity_check")] != ["ok"]:
            raise StateIntegrityError("canonical database integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StateIntegrityError("canonical database foreign-key check failed")
        for row in conn.execute("SELECT * FROM records"):
            payload = json.loads(row["payload_json"])
            kwargs = dict(payload)
            kwargs.pop("record_sha256")
            kwargs.pop("content_sha256")
            for field in ("provenance_refs", "derived_from", "transformation_lineage_sha256s",
                          "taint_labels", "contradicts"):
                if field in kwargs:
                    kwargs[field] = tuple(kwargs[field])
            record = MemoryRecord.build(**kwargs)
            if (record.to_dict() != payload or record.record_sha256 != row["record_sha256"] or
                record.record_id != row["record_id"] or record.revision != row["revision"] or
                record.source_id != row["source_id"] or record.scope_id != row["scope_id"] or
                record.classification != row["classification"] or record.expires_at != row["expires_at"]):
                raise StateIntegrityError("canonical record content or identity hash mismatch")
        receipts: list[tuple[dict[str, Any], bool]] = []
        for row in conn.execute("SELECT * FROM receipt_outbox ORDER BY rowid"):
            payload = json.loads(row["receipt_json"])
            receipt = _receipt_from_payload(payload).to_dict()
            if (receipt["operation_id"] != row["operation_id"] or
                receipt["action_authority"] is not False or receipt["execution_authority"] is not False):
                raise StateIntegrityError("backup can restore only zero-authority memory receipts")
            receipts.append((receipt, bool(row["published"])))
        return receipts


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    prepare_state_file(path)
    with _locked(path, write=True) as (handle, parent):
        data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        remaining = memoryview(data)
        while remaining:
            written = handle.write(remaining)
            if not written:
                raise OSError("metadata write made no progress")
            remaining = remaining[written:]
        os.fsync(handle.fileno())
        if parent is not None:
            os.fsync(parent)


def backup(source: Path, destination: Path, *, preserve_incomplete_tail: bool = False) -> dict[str, Any]:
    source = _safe_root(source)
    destination = destination.expanduser().absolute()
    if destination.is_relative_to(source):
        raise ValueError("backup destination must be outside the active state root")
    destination.mkdir(mode=0o700)  # no overwrite, including an empty existing directory
    started = datetime.now(UTC).isoformat()
    files: list[str] = []
    incomplete: list[str] = []

    def capture_rows(path: Path, name: str) -> list[dict[str, Any]]:
        rows, tail = recoverable_jsonl_prefix(path)
        if tail and not preserve_incomplete_tail:
            raise StateIntegrityError(f"incomplete audit tail in {name}; explicit preservation required")
        if tail:
            raw = "audit/" + name.replace("/", "-") + ".bin"
            if raw not in files:
                _copy(path, destination / raw)
                files.append(raw)
                incomplete.append(raw)
        return rows

    db = source / CANONICAL
    if db.exists():
        # Validate path custody, then use SQLite's online snapshot API rather
        # than copying database/WAL bytes from a running process.
        _hash(db)
        target = destination / CANONICAL
        prepare_state_file(target)
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=30)) as original:
            with closing(sqlite3.connect(target)) as snapshot:
                original.backup(snapshot)
        with _locked(target, write=True) as (handle, parent):
            os.fsync(handle.fileno())
            if parent is not None:
                os.fsync(parent)
        receipts = _database(target)
        originals = capture_rows(source / MEMORY_LEDGER, "spine-ledger-mandala-receipts.jsonl")
        for receipt, published in receipts:
            matches = [row for row in originals if row.get("receipt_id") == receipt["receipt_id"]]
            if published and (len(matches) != 1 or matches[0] != receipt):
                raise StateIntegrityError("published canonical data lacks its exact durable receipt")
            if matches and (len(matches) != 1 or matches[0] != receipt):
                raise StateIntegrityError("canonical memory receipt collision")
            if published:
                append_jsonl(destination / MEMORY_LEDGER, receipt, identity_field="receipt_id")
        prepare_state_file(destination / MEMORY_LEDGER)
        files.extend([CANONICAL, MEMORY_LEDGER])
    for name in ["curiosity/artifacts.jsonl", "curiosity/return-pointers.jsonl"]:
        path = source / name
        if path.exists():
            rows = capture_rows(path, name)
            prepare_state_file(destination / name)
            for row in rows:
                append_jsonl(destination / name, row)
            files.append(name)
    # All effect, decision, binding, lease and session evidence is archived
    # outside active runtime paths. Claim markers and credentials are excluded.
    ledger = source / "spine-v0.1/ledger"
    if ledger.exists():
        for path in sorted(ledger.glob("*.jsonl")):
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}\.jsonl", path.name) is None:
                raise StateIntegrityError("unexpected ledger filename")
            name = "audit/" + path.name
            rows = capture_rows(path, "spine-ledger-" + path.name)
            prepare_state_file(destination / name)
            for row in rows:
                append_jsonl(destination / name, row)
            files.append(name)
    manifest = {
        "schema_version": FORMAT, "canonical_schema_version": SCHEMA_VERSION,
        "backup_id": str(uuid.uuid4()), "capture_started_at": started,
        "capture_finished_at": datetime.now(UTC).isoformat(),
        "authority_restored": False, "configuration_restored": False,
        "derived_indexes_restored": False, "encrypted": False,
        "incomplete_audit_files": sorted(set(incomplete)),
        "files": {name: _hash(destination / name) for name in sorted(files)},
    }
    _write_json(destination / "manifest.json", manifest)
    sync_directory(destination.parent)
    verify_backup(destination)
    return manifest


def verify_backup(source: Path) -> dict[str, Any]:
    source = _safe_root(source)
    with _locked(source / "manifest.json", write=False) as (handle, _parent):
        manifest = json.load(handle)
    expected = {"schema_version", "canonical_schema_version", "backup_id", "capture_started_at",
                "capture_finished_at", "authority_restored", "configuration_restored",
                "derived_indexes_restored", "encrypted", "incomplete_audit_files", "files"}
    if (not isinstance(manifest, dict) or set(manifest) != expected or
        manifest["schema_version"] != FORMAT or manifest["canonical_schema_version"] != SCHEMA_VERSION or
        any(manifest[key] is not False for key in ["authority_restored", "configuration_restored",
                                                  "derived_indexes_restored", "encrypted"])):
        raise StateIntegrityError("unsupported or authority-bearing backup format")
    files = manifest["files"]
    if not isinstance(files, dict) or len(files) > 512:
        raise StateIntegrityError("invalid backup inventory")
    for name, identity in files.items():
        if not isinstance(name, str) or not (name in DATA_FILES or
            re.fullmatch(r"audit/[a-z0-9][a-z0-9-]{0,150}\.jsonl(?:\.bin)?", name)):
            raise StateIntegrityError("unexpected backup path")
        if not isinstance(identity, dict) or set(identity) != {"sha256", "size"}:
            raise StateIntegrityError("invalid backup file identity")
        if (not isinstance(identity["sha256"], str) or
            re.fullmatch(r"[0-9a-f]{64}", identity["sha256"]) is None or
            type(identity["size"]) is not int or identity["size"] < 0):
            raise StateIntegrityError("invalid backup hash or size")
        if _hash(source / name) != identity:
            raise StateIntegrityError(f"backup hash or size mismatch: {name}")
        if name.endswith(".jsonl"):
            read_jsonl(source / name)
    if CANONICAL in files:
        receipts = _database(source / CANONICAL)
        expected_receipts = [receipt for receipt, published in receipts if published]
        if MEMORY_LEDGER not in files or read_jsonl(source / MEMORY_LEDGER) != expected_receipts:
            raise StateIntegrityError("active restored ledger must contain only exact published memory receipts")
    elif MEMORY_LEDGER in files:
        raise StateIntegrityError("a restored memory ledger requires its canonical database")
    incomplete = manifest["incomplete_audit_files"]
    if (not isinstance(incomplete, list) or
        any(not isinstance(name, str) or not name.endswith(".jsonl.bin") or name not in files
            for name in incomplete) or len(incomplete) != len(set(incomplete))):
        raise StateIntegrityError("invalid incomplete-audit inventory")
    curiosity = CuriosityStore(source / "curiosity")
    targets = {item.curiosity_artifact_sha256 for item in curiosity.artifacts()}
    if any(pointer.artifact_sha256 not in targets for pointer in curiosity.return_pointers()):
        raise StateIntegrityError("curiosity return pointer has no verified artifact")
    return manifest


def restore(source: Path, destination: Path) -> dict[str, Any]:
    source = source.expanduser().absolute()
    destination = destination.expanduser().absolute()
    manifest = verify_backup(source)  # no destination writes until all input checks pass
    if destination.is_relative_to(source):
        raise ValueError("restore destination must be outside the backup")
    destination.mkdir(mode=0o700)
    for name in manifest["files"]:
        target = "recovered-" + name if name.startswith("audit/") else name
        _copy(source / name, destination / target)
    if CANONICAL in manifest["files"]:
        _database(destination / CANONICAL)
    receipt = {"schema_version": "phios.data-restore.v1", "backup_id": manifest["backup_id"],
               "restore_id": str(uuid.uuid4()), "authority_restored": False,
               "configuration_restored": False, "derived_indexes_restored": False,
               "incomplete_audit_files": manifest["incomplete_audit_files"],
               "canonical_schema_version": SCHEMA_VERSION, "release_ready": False}
    _write_json(destination / "restored-state.json", receipt)
    sync_directory(destination.parent)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(prog="phi-state", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup", help="Create a private data-only backup in a new directory")
    create.add_argument("--state-root", type=Path, default=configured_state_root())
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--preserve-incomplete-tail", action="store_true",
                        help="Archive incomplete final audit rows outside active paths; source stays held")
    inspect = commands.add_parser("verify", help="Verify all backup hashes and canonical integrity")
    inspect.add_argument("backup", type=Path)
    recover = commands.add_parser("restore", help="Restore data into a fresh state root; authority stays held")
    recover.add_argument("backup", type=Path)
    recover.add_argument("--new-state-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup(args.state_root, args.output,
                            preserve_incomplete_tail=args.preserve_incomplete_tail)
        elif args.command == "verify":
            result = verify_backup(args.backup)
        else:
            result = restore(args.backup, args.new_state_root)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        print(f"State operation failed; preserve any partial destination for review: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
