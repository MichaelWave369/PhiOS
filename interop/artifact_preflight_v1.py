"""PhiOS R5 local artifact integrity preflight.

This is an actual bounded file hashing operation and receipt generator, NOT a
signature verifier, license audit, compatibility test, updater or installer.
All authority claims in supplied manifests must explicitly be false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from shell_catalog_v1 import read_catalog

MAX_MANIFEST = 16 * 1024
MAX_ARTIFACT = 256 * 1024 * 1024
MANIFEST_KEYS = {"schema", "app_id", "repository", "target", "source_commit_sha", "artifact", "assertions"}
ARTIFACT_KEYS = {"file_name", "size_bytes", "sha256"}
ASSERTION_KEYS = {"publisher_signature_verified", "license_cleared", "device_compatibility_verified",
                  "operator_approved", "install_authority", "requested_action"}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,119}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _read_regular_file(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit or info.st_size < 1:
            raise ValueError("Manifest is not a bounded regular file")
        content = os.read(fd, limit + 1)
        if len(content) != info.st_size or len(content) > limit:
            raise ValueError("Manifest changed or exceeded size limit")
        return content
    finally:
        os.close(fd)


def read_proposal(path: Path) -> dict:
    try:
        obj = json.loads(_read_regular_file(path, MAX_MANIFEST).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Manifest must be valid UTF-8 JSON") from error
    if not isinstance(obj, dict) or set(obj) != MANIFEST_KEYS or obj["schema"] != "phios.artifact-intake.v1":
        raise ValueError("Unsupported artifact-intake manifest")
    if type(obj["app_id"]) is not str or not re.fullmatch(r"github:[0-9]{1,20}", obj["app_id"]):
        raise ValueError("Invalid catalog identity")
    catalog = read_catalog()
    matched = next((entry for entry in catalog["apps"] if entry["id"] == obj["app_id"]), None)
    if not matched or obj["repository"] != matched["repository"]:
        raise ValueError("Source identity must match the pinned public catalog")
    if obj["target"] not in ("web", "android", "linux") or (
        type(obj["source_commit_sha"]) is not str or not HEX40.fullmatch(obj["source_commit_sha"])
    ):
        raise ValueError("Unknown runtime or unpinned source commit")
    artifact = obj["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_KEYS:
        raise ValueError("Invalid exact artifact fields")
    if not isinstance(artifact["file_name"], str) or not SAFE_NAME.fullmatch(artifact["file_name"]):
        raise ValueError("Invalid artifact basename")
    if type(artifact["size_bytes"]) is not int or not (1 <= artifact["size_bytes"] <= MAX_ARTIFACT):
        raise ValueError("Artifact size is invalid or exceeds 256 MiB")
    if not isinstance(artifact["sha256"], str) or not HEX64.fullmatch(artifact["sha256"]):
        raise ValueError("Artifact SHA-256 must be exact lowercase hexadecimal")
    assertions = obj["assertions"]
    if not isinstance(assertions, dict) or set(assertions) != ASSERTION_KEYS or assertions != {
        "publisher_signature_verified": False,
        "license_cleared": False,
        "device_compatibility_verified": False,
        "operator_approved": False,
        "install_authority": False,
        "requested_action": "verify_only",
    }:
        raise ValueError("Integrity preflight cannot grant review, signature or installation authority")
    return obj


def verify_artifact(manifest: dict, path: Path) -> dict:
    artifact = manifest["artifact"]
    if path.name != artifact["file_name"]:
        raise ValueError("Selected file does not match expected artifact basename")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != artifact["size_bytes"]:
            raise ValueError("Artifact is not a regular file with expected byte length")
        if before.st_size > MAX_ARTIFACT:
            raise ValueError("Artifact exceeds 256 MiB")
        sha = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, min(1024 * 1024, before.st_size - total + 1))
            if not block:
                break
            total += len(block)
            if total > artifact["size_bytes"]:
                raise ValueError("Artifact changed during verification")
            sha.update(block)
        after = os.fstat(fd)
        if (total != artifact["size_bytes"] or total != after.st_size or
            before.st_ino != after.st_ino or before.st_dev != after.st_dev or
            before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("Artifact changed during verification")
    finally:
        os.close(fd)
    if sha.hexdigest() != artifact["sha256"]:
        raise ValueError("Artifact SHA-256 mismatches declared digest")
    return {
        "schema": "phios.artifact-integrity-receipt.v1",
        "app_id": manifest["app_id"],
        "repository": manifest["repository"],
        "source_commit_sha": manifest["source_commit_sha"],
        "target": manifest["target"],
        "artifact": dict(artifact),
        "content_sha256_matches_manifest": True,
        "publisher_signature_verified": False,
        "license_cleared": False,
        "device_compatibility_verified": False,
        "install_authority": False,
        "effect_performed": False,
        "next_gate": "independent publisher identity, license, compatibility, and operator install review",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify local artifact bytes; NEVER installs software")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = verify_artifact(read_proposal(args.manifest), args.artifact)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f"Refused integrity preflight: {error}", file=sys.stderr)
        sys.exit(1)
