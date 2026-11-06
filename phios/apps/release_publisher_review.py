"""PhiOS R5B offline Ed25519 review bound to a v0.50 release install proposal.

This actually verifies a detached signature under an externally supplied raw
Ed25519 public key and an independently passed SHA-256 key fingerprint. It
never fetches keys, trusts a key embedded in a manifest, installs applications,
or treats a signature as device compatibility or release approval.
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
from typing import Any

from .release_install_proposal import ReleaseInstallProposalRecord

DOMAIN = b"PhiOS/release-publisher-statement/v1\x00"
STATEMENT_SCHEMA = "phios.release_publisher_statement.v0.1"
REVIEW_SCHEMA = "phios.release_publisher_review.v0.1"
MAX_JSON = 32768
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
KEY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
STATEMENT_FIELDS = frozenset({
    "schema", "publisher_key_id", "app_id", "app_version",
    "repository_url", "commit_sha", "release_install_proposal_sha256",
    "package_plan_sha256", "manifest_sha256", "artifact_set_sha256",
    "dependency_review_sha256", "compatibility_review_sha256",
    "rollback_rehearsal_sha256", "install_authority", "update_authority",
    "rollback_authority",
})


def _strict_json_bytes(value: dict[str, Any]) -> bytes:
    try:
        wire = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Publisher statement cannot be canonicalized") from exc
    if len(wire) > MAX_JSON:
        raise ValueError("Publisher statement exceeds 32 KiB")
    return wire


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase 64-hex SHA-256")
    return value


def _validate_statement(
    proposal: ReleaseInstallProposalRecord, statement_value: Any
) -> tuple[dict[str, Any], bytes]:
    if type(statement_value) is not dict or set(statement_value) != STATEMENT_FIELDS:
        raise ValueError("Publisher statement has missing or unknown fields")
    statement: dict[str, Any] = statement_value
    if statement["schema"] != STATEMENT_SCHEMA:
        raise ValueError("Unrecognized publisher statement schema")
    key_id = statement["publisher_key_id"]
    if not isinstance(key_id, str) or KEY_ID.fullmatch(key_id) is None:
        raise ValueError("Invalid publisher key identifier")
    expected = {
        "app_id": proposal.app_id,
        "app_version": proposal.app_version,
        "repository_url": proposal.repository_url,
        "commit_sha": proposal.commit_sha,
        "release_install_proposal_sha256": proposal.sha256(),
        "package_plan_sha256": proposal.package_plan_sha256,
        "manifest_sha256": proposal.manifest_sha256,
        "artifact_set_sha256": proposal.artifact_set_sha256,
    }
    for field, required in expected.items():
        if type(statement[field]) is not str or statement[field] != required:
            raise ValueError(f"Signed {field} does not bind the exact release proposal")
    for field in (
        "dependency_review_sha256",
        "compatibility_review_sha256",
        "rollback_rehearsal_sha256",
    ):
        _required_sha(statement[field], field)
    for field in ("install_authority", "update_authority", "rollback_authority"):
        if statement[field] is not False:
            raise ValueError(f"Signature statement must not assert {field}")
    return statement, _strict_json_bytes(statement)


def review_signed_release(
    proposal_value: Any,
    statement_value: Any,
    *,
    signature: bytes,
    publisher_public_key: bytes,
    independently_pinned_key_sha256: str,
    expected_key_id: str,
) -> dict[str, Any]:
    """Verify an exact proposal and signed claims; retain ALL install holds.

    A caller's key fingerprint is a consistency check, not a proof that the
    caller selected a trustworthy key. Those origins need separate review.
    """
    proposal = ReleaseInstallProposalRecord.from_dict(proposal_value)
    statement, wire = _validate_statement(proposal, statement_value)
    pinned = _required_sha(independently_pinned_key_sha256, "pinned key fingerprint")
    if not isinstance(expected_key_id, str) or not KEY_ID.fullmatch(expected_key_id):
        raise ValueError("Externally expected publisher key ID is invalid")
    if statement["publisher_key_id"] != expected_key_id:
        raise ValueError("Signed key ID does not match independently expected key ID")
    if type(publisher_public_key) is not bytes or len(publisher_public_key) != 32:
        raise ValueError("Raw Ed25519 public key must be exactly 32 bytes")
    if hashlib.sha256(publisher_public_key).hexdigest() != pinned:
        raise ValueError("Publisher public key does not match independently supplied pin")
    if type(signature) is not bytes or len(signature) != 64:
        raise ValueError("Detached Ed25519 signature must be exactly 64 bytes")

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ValueError(
            "Ed25519 review requires cryptography; no fallback to weak verification"
        ) from exc
    try:
        Ed25519PublicKey.from_public_bytes(publisher_public_key).verify(
            signature, DOMAIN + wire
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Detached Ed25519 signature invalid for supplied pinned key") from exc

    report = {
        "schema": REVIEW_SCHEMA,
        "status": "SIGNATURE_VALID_UNDER_CALLER_PIN_RELEASE_STILL_HELD",
        "app_id": proposal.app_id,
        "app_version": proposal.app_version,
        "repository_url": proposal.repository_url,
        "commit_sha": proposal.commit_sha,
        "release_install_proposal_sha256": proposal.sha256(),
        "package_plan_sha256": proposal.package_plan_sha256,
        "artifact_set_sha256": proposal.artifact_set_sha256,
        "publisher_key_id": expected_key_id,
        "pinned_public_key_sha256": pinned,
        "signed_statement_sha256": hashlib.sha256(wire).hexdigest(),
        "signature_valid_under_supplied_key": True,
        "publisher_identity_independently_verified": False,
        "source_commit_independently_authenticated": False,
        "dependency_compatibility_verified": False,
        "device_compatibility_verified": False,
        "license_distribution_review_cleared": False,
        "sandbox_and_permission_review_cleared": False,
        "rollback_rehearsal_independently_verified": False,
        "install_authority": False,
        "launch_authority": False,
        "update_authority": False,
        "rollback_authority": False,
        "operations_performed": [],
        "remaining_gate": (
            "external key provenance, source/artifact correspondence, dependency/license/"
            "device review, independent rollback rehearsal, and explicit device-local "
            "install approval through the existing phi-app App Platform"
        ),
    }
    report["review_sha256"] = hashlib.sha256(_strict_json_bytes(report)).hexdigest()
    return report


def _read_regular(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise ValueError("Refusing symbolic-link review input")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        item = os.fstat(fd)
        if not stat.S_ISREG(item.st_mode) or item.st_size <= 0 or item.st_size > limit:
            raise ValueError("Review input is not a bounded regular file")
        data = os.read(fd, limit + 1)
        if len(data) != item.st_size:
            raise ValueError("Review input changed during read")
        return data
    finally:
        os.close(fd)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_regular(path, MAX_JSON).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Review input is not UTF-8 JSON") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Ed25519 release review. Never installs or approves anything."
    )
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--trusted-key-sha256", required=True)
    parser.add_argument("--expected-key-id", required=True)
    args = parser.parse_args(argv)
    receipt = review_signed_release(
        _read_json(args.proposal),
        _read_json(args.statement),
        signature=_read_regular(args.signature, 64),
        publisher_public_key=_read_regular(args.public_key, 32),
        independently_pinned_key_sha256=args.trusted_key_sha256,
        expected_key_id=args.expected_key_id,
    )
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"Release still held: {exc}", file=sys.stderr)
        sys.exit(1)
