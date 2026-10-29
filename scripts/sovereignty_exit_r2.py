#!/usr/bin/env python3
"""R2: opt-in portable PhiOS data snapshots with independent read/restore.

Bundle creation reviews a phi-state backup through PhiOS. Verification and
extraction of the resulting ZIP require only this script, the v0.1 ZIP helper,
and Python 3.11+ standard library. Nothing is imported from PhiOS for reads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath

from sovereignty_exit_v01 import pack, verified_files

SCHEMA = "phios.sovereignty.exit.r2.v0.1"
BACKUP_SCHEMA = "phios.data-backup.v1"
ALLOWED = frozenset({
    "memory/canonical.sqlite3",
    "spine-v0.1/ledger/mandala-receipts.jsonl",
    "curiosity/artifacts.jsonl",
    "curiosity/return-pointers.jsonl",
})
OMISSIONS = (
    "PhiShell browser storage and settings (no browser export adapter)",
    "GitPorch repositories and snapshots (separate project; no adapter)",
    "enabled configuration, keys, tokens, credentials and grants",
    "derived indexes, embedding models and model weights",
    "other application state and external provider accounts",
    "host boot, network-disconnected operation and OS reinstall",
)
REQUIRED_MANIFEST = frozenset({
    "schema_version", "canonical_schema_version", "backup_id",
    "capture_started_at", "capture_finished_at", "authority_restored",
    "configuration_restored", "derived_indexes_restored", "encrypted",
    "incomplete_audit_files", "files",
})
AUDIT_RE = re.compile(r"audit/[a-z0-9][a-z0-9-]{0,150}\\.jsonl(?:\\.bin)?\\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\\Z")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _approved_path(name: str) -> bool:
    return name in ALLOWED or AUDIT_RE.fullmatch(name) is not None


def inventory() -> dict[str, object]:
    """Static, reviewed scope only; does not probe the operator's machine."""
    return {
        "schema": SCHEMA,
        "status": "UNVERIFIED",
        "candidateAdapter": "phi-state verified data-only backup",
        "supportedPaths": sorted(ALLOWED) + ["audit/*.jsonl", "audit/*.jsonl.bin"],
        "omissions": list(OMISSIONS),
        "automaticDiscovery": False,
        "hostScan": False,
        "authorityGranted": False,
        "exitVerified": False,
    }


def verify_bundle(path: Path) -> dict[str, object]:
    """Stdlib-only verification: ZIP hashes + exact nested backup inventory.

    This verifies internal integrity, not authenticity, live DB semantics or
    whether the producer actually captured every relevant application store.
    """
    content = dict(verified_files(path))
    if "manifest.json" not in content:
        raise ValueError("missing embedded phi-state manifest")
    try:
        manifest = json.loads(content["manifest.json"].decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid embedded backup manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != REQUIRED_MANIFEST:
        raise ValueError("unsupported backup manifest structure")
    if manifest["schema_version"] != BACKUP_SCHEMA:
        raise ValueError("unsupported backup schema")
    if type(manifest["canonical_schema_version"]) is not int or manifest["canonical_schema_version"] != 1:
        raise ValueError("unsupported memory schema")
    if any(manifest[k] is not False for k in (
        "authority_restored", "configuration_restored", "derived_indexes_restored", "encrypted"
    )):
        raise ValueError("backup carries unsupported state or authority flags")
    files = manifest["files"]
    if not isinstance(files, dict) or len(files) > 512:
        raise ValueError("invalid nested file inventory")
    if set(content) != set(files) | {"manifest.json"}:
        raise ValueError("incomplete or unexpected backup members")
    for name, meta in files.items():
        if not isinstance(name, str) or not _approved_path(name):
            raise ValueError("unapproved backup member")
        if not isinstance(meta, dict) or set(meta) != {"size", "sha256"}:
            raise ValueError("invalid nested file metadata")
        data = content[name]
        if (type(meta["size"]) is not int or meta["size"] != len(data)
                or not isinstance(meta["sha256"], str)
                or HASH_RE.fullmatch(meta["sha256"]) is None
                or _digest(data) != meta["sha256"]):
            raise ValueError("nested backup checksum or size mismatch")
    incomplete = manifest["incomplete_audit_files"]
    if (not isinstance(incomplete, list) or len(set(
            item for item in incomplete if isinstance(item, str))) != len(incomplete)
            or any(not isinstance(item, str) or not item.endswith(".jsonl.bin")
                   or item not in files for item in incomplete)):
        raise ValueError("invalid incomplete-audit inventory")
    if ("spine-v0.1/ledger/mandala-receipts.jsonl" in files
            and "memory/canonical.sqlite3" not in files):
        raise ValueError("orphaned memory receipt ledger")
    return {
        "schema": SCHEMA,
        "status": "PARTIAL" if files else "UNVERIFIED",
        "producerBackupSchema": BACKUP_SCHEMA,
        "contentFiles": len(files),
        "embeddedManifestSha256": _digest(content["manifest.json"]),
        "internalHashesVerified": True,
        "independentReadable": True,
        "restoredToIndependentHost": False,
        "runtimeStateValidated": False,
        "captureCompletenessVerified": False,
        "hostScan": False,
        "authorityGranted": False,
        "exitVerified": False,
        "omissions": list(OMISSIONS),
    }


def bundle(backup_dir: Path, output: Path) -> dict[str, object]:
    """Requires the full PhiOS producer on the exporting machine only."""
    from phios.state_recovery import verify_backup
    backup_dir = backup_dir.expanduser().absolute()
    output = output.expanduser().absolute()
    if output.is_relative_to(backup_dir):
        raise ValueError("output archive must be outside the phi-state backup")
    verify_backup(backup_dir)  # verifies canonical DB, receipts, hashes, custody
    pack(backup_dir, output)
    return verify_bundle(output)


def restore_snapshot(bundle_path: Path, output: Path) -> dict[str, object]:
    """Extract a private, inert snapshot; never activate state or grants."""
    receipt = verify_bundle(bundle_path)
    destination = output.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("restore destination already exists")
    items = verified_files(bundle_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".phi-exit-r2-") as staging:
        root = Path(staging) / "snapshot"
        root.mkdir(mode=0o700)
        for name, data in items:
            target = root.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(root, destination)
    return {
        **receipt,
        "restoredToIndependentHost": False,  # runtime cannot attest host identity
        "snapshotExtracted": True,
        "activeStateRestored": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PhiOS R2 portable data-only snapshot (unencrypted)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    export = sub.add_parser("bundle")
    export.add_argument("--verified-phi-state-backup", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--i-approve-unencrypted-export", action="store_true")
    check = sub.add_parser("verify")
    check.add_argument("--bundle", type=Path, required=True)
    restore = sub.add_parser("extract")
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result = inventory()
        elif args.command == "bundle":
            if not args.i_approve_unencrypted_export:
                raise ValueError("explicit unencrypted export approval required")
            result = bundle(args.verified_phi_state_backup, args.output)
        elif args.command == "verify":
            result = verify_bundle(args.bundle)
        else:
            result = restore_snapshot(args.bundle, args.output)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.exit(1, "HELD: " + str(exc) + "\\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
