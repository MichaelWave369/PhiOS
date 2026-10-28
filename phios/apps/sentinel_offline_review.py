"""PhiOS Security Center v0.2: explicit, offline signed-pack review.

Reviews the exact bytes of a local FieldShield v0.3 pack/manifest/trust-store
against an independently supplied 32-byte Ed25519 public-key SHA-256 pin.
No scan, subprocess, network, mutations, trust enrollment, or launch authority.

A valid signature proves possession of a paired private key, NOT spyware
accuracy, publisher identity, OS integrity, or current host security.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

MAX_PACK = 2_000_000
MAX_MANIFEST = 16_384
MAX_TRUST = 131_072
DOMAIN = b"FieldShield Sentinel Signed IOC v1\x00"
HEADER = frozenset({"schema", "publisher", "key_id", "pack_sha256", "issued_at", "expires_at"})
SIGNED = HEADER | {"signature_b64"}
ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _read(path: Path, limit: int) -> bytes:
    """Take one bounded snapshot and refuse symlinks on supported platforms."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Symlink inputs are not allowed")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_BINARY", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("Input must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as handle:
            data = handle.read(limit + 1)
        after = os.fstat(fd)
        if (len(data) > limit or len(data) != before.st_size
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns):
            raise ValueError("Input changed during read or exceeded size limit")
        return data
    finally:
        os.close(fd)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON property")
        obj[key] = value
    return obj


def _json(raw: bytes, name: str) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("Non-finite JSON constant")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(name + " must be strict UTF-8 JSON") from exc
    if type(data) is not dict:
        raise ValueError(name + " must be a JSON object")
    return data


def _time(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError(name + " requires a timezone-aware timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(name + " is not ISO-8601") from exc
    if result.tzinfo is None:
        raise ValueError(name + " requires timezone")
    return result.astimezone(timezone.utc)


def _decode64(value: Any, length: int, name: str) -> bytes:
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError(name + " requires canonical base64")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(name + " requires canonical base64") from exc
    if len(data) != length or base64.b64encode(data).decode("ascii") != value:
        raise ValueError(name + " requires canonical base64 and expected length")
    return data


def _check_trust(policy: dict[str, Any], publisher: str, key_id: str,
                 pack_digest: str, signed_at: datetime) -> bytes:
    if set(policy) != {"schema", "publishers"} or policy["schema"] != "fieldshield.trust-store.v1":
        raise ValueError("Unknown trust-store schema")
    publishers = policy["publishers"]
    if not isinstance(publishers, list) or len(publishers) > 100:
        raise ValueError("Invalid publishers roster")
    seen_publishers: set[str] = set()
    selected: dict[str, Any] | None = None
    for item in publishers:
        if (type(item) is not dict or
                set(item) != {"id", "keys", "blocked_pack_sha256", "minimum_issued_at"} or
                not isinstance(item["id"], str) or not ID.fullmatch(item["id"]) or
                item["id"] in seen_publishers):
            raise ValueError("Malformed/duplicate trust publisher")
        seen_publishers.add(item["id"])
        if item["id"] == publisher:
            selected = item
    if selected is None:
        raise ValueError("Publisher not in locally supplied trust policy")
    blocked = selected["blocked_pack_sha256"]
    if (not isinstance(blocked, list) or
            any(not isinstance(s, str) or not SHA256.fullmatch(s) for s in blocked)):
        raise ValueError("Invalid pack blocklist")
    if pack_digest in blocked:
        raise ValueError("Pack explicitly blocked by trust policy")
    if signed_at < _time(selected["minimum_issued_at"], "minimum_issued_at"):
        raise ValueError("Signature predates local trust minimum issuance date")
    keys = selected["keys"]
    if not isinstance(keys, list) or len(keys) > 100:
        raise ValueError("Invalid trust key roster")
    seen_keys: set[str] = set()
    chosen: bytes | None = None
    for item in keys:
        if (type(item) is not dict or
                set(item) != {"id", "algorithm", "state", "public_key_b64"} or
                not isinstance(item["id"], str) or not ID.fullmatch(item["id"]) or
                item["id"] in seen_keys or item["algorithm"] != "ed25519" or
                item["state"] not in {"trusted", "revoked"}):
            raise ValueError("Malformed/duplicate trusted key entry")
        seen_keys.add(item["id"])
        public = _decode64(item["public_key_b64"], 32, "public_key_b64")
        if item["id"] == key_id:
            if item["state"] == "revoked":
                raise ValueError("Locally revoked signing key")
            chosen = public
    if chosen is None:
        raise ValueError("Unknown signing key in trust policy")
    return chosen


def review_signed_pack(*, pack_bytes: bytes, manifest_bytes: bytes, trust_bytes: bytes,
                       expected_key_sha256: str, now: datetime | None = None) -> dict[str, Any]:
    """Produce an informational cryptographic review, NEVER security authority."""
    if (len(pack_bytes) > MAX_PACK or len(manifest_bytes) > MAX_MANIFEST
            or len(trust_bytes) > MAX_TRUST):
        raise ValueError("Input exceeds bounded size")
    if not isinstance(expected_key_sha256, str) or not SHA256.fullmatch(expected_key_sha256):
        raise ValueError("Expected external Ed25519 key SHA-256 pin is required")
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Review clock must be timezone aware")
    now = now.astimezone(timezone.utc)
    manifest = _json(manifest_bytes, "Manifest")
    if (set(manifest) != SIGNED or manifest.get("schema") != "fieldshield.signed-ioc.v1"
            or any(not isinstance(manifest.get(k), str) or not ID.fullmatch(manifest[k])
                   for k in ("publisher", "key_id"))
            or not isinstance(manifest["pack_sha256"], str)
            or not SHA256.fullmatch(manifest["pack_sha256"])):
        raise ValueError("Malformed FieldShield signed manifest")
    issued = _time(manifest["issued_at"], "signed issued_at")
    expires = _time(manifest["expires_at"], "expires_at")
    if expires <= issued or issued > now or expires <= now:
        raise ValueError("Signed manifest not valid at review time")
    pack_digest = hashlib.sha256(pack_bytes).hexdigest()
    if pack_digest != manifest["pack_sha256"]:
        raise ValueError("Signed pack digest mismatch")
    public = _check_trust(_json(trust_bytes, "Trust store"),
                          manifest["publisher"], manifest["key_id"],
                          pack_digest, issued)
    if hashlib.sha256(public).hexdigest() != expected_key_sha256:
        raise ValueError("Publisher public key does not match out-of-band SHA-256 pin")
    signature = _decode64(manifest["signature_b64"], 64, "signature_b64")
    payload = {key: manifest[key] for key in HEADER}
    wire = DOMAIN + json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("ascii")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ValueError("Ed25519 verification needs optional cryptography dependency") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, wire)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Ed25519 signature invalid for pinned key") from exc

    pack = _json(pack_bytes, "IOC pack")
    if (pack.get("schema") != "fieldshield.ioc-pack.v1"
            or not isinstance(pack.get("source"), str) or not pack["source"].strip()
            or not isinstance(pack.get("indicators"), list)
            or not 0 < len(pack["indicators"]) <= 100_000):
        raise ValueError("Signed bytes are not a supported Sentinel IOC pack")
    if _time(pack.get("issued_at"), "pack issued_at") > issued:
        raise ValueError("Pack issuance postdates signed manifest")
    result: dict[str, Any] = {
        "schema": "phios.security_center.offline_pack_review.v0.2",
        "status": "ED25519_VALID_UNDER_CALLER_SUPPLIED_PIN_NO_HOST_SCAN",
        "reviewed_at": now.isoformat(),
        "pack_sha256": pack_digest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "trust_policy_sha256": hashlib.sha256(trust_bytes).hexdigest(),
        "external_pinned_key_sha256": expected_key_sha256,
        "publisher_claim": manifest["publisher"],
        "key_id": manifest["key_id"],
        "manifest_expires_at": expires.isoformat(),
        "indicators_claimed": len(pack["indicators"]),
        "signature_valid_for_pinned_key": True,
        "external_key_pin_independently_authenticated_by_phios": False,
        "publisher_real_world_identity_authenticated": False,
        "indicator_accuracy_verified": False,
        "host_security_observed": False,
        "scan_performed": False,
        "network_access_performed": False,
        "launch_authority": False,
        "gateway_authority": False,
        "effects_performed": [],
        "limitations": "Authenticity to a caller-supplied pin only; no host scan or trust-root authentication.",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PhiOS offline review of a locally signed Sentinel IOC pack (no scan)"
    )
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--expected-public-key-sha256", required=True,
                        help="SHA-256 of 32-byte key checked through a separate trusted channel")
    parser.add_argument("--i-approve-local-review", action="store_true",
                        help="I authorize read-only access to these three local files")
    args = parser.parse_args(argv)
    try:
        if not args.i_approve_local_review:
            raise ValueError("Explicit --i-approve-local-review is required")
        result = review_signed_pack(
            pack_bytes=_read(args.pack, MAX_PACK),
            manifest_bytes=_read(args.signature, MAX_MANIFEST),
            trust_bytes=_read(args.trust, MAX_TRUST),
            expected_key_sha256=args.expected_public_key_sha256,
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print("PhiOS offline pack review refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
