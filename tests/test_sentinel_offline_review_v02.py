"""Security Center v0.2 signed IOC pack review: synthetic and fail-closed cases."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phios.apps.sentinel_offline_review import DOMAIN, main, review_signed_pack

NOW = datetime(2026, 10, 28, 19, 0, tzinfo=timezone.utc)


def wire(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def example() -> tuple[bytes, bytes, bytes, str, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()  # Ephemeral in-memory signing key ONLY
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    digest = hashlib.sha256(pub).hexdigest()
    pack = wire({
        "schema": "fieldshield.ioc-pack.v1",
        "source": "Synthetic test pack only",
        "issued_at": "2026-01-01T00:00:00Z",
        "indicators": [{
            "id": "test-1", "kind": "domain", "value": "test.example.invalid",
            "confidence": "low", "reference": "https://www.rfc-editor.org/rfc/rfc2606",
        }],
    })
    header: dict[str, str] = {
        "schema": "fieldshield.signed-ioc.v1",
        "publisher": "fixture-lab",
        "key_id": "fixture-1",
        "pack_sha256": hashlib.sha256(pack).hexdigest(),
        "issued_at": "2026-02-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
    }
    manifest = wire({
        **header,
        "signature_b64": base64.b64encode(key.sign(DOMAIN + wire(header))).decode("ascii"),
    })
    trust = wire({
        "schema": "fieldshield.trust-store.v1",
        "publishers": [{
            "id": "fixture-lab", "minimum_issued_at": "2026-01-01T00:00:00Z",
            "blocked_pack_sha256": [],
            "keys": [{
                "id": "fixture-1", "algorithm": "ed25519", "state": "trusted",
                "public_key_b64": base64.b64encode(pub).decode("ascii"),
            }],
        }],
    })
    return pack, manifest, trust, digest, key


def inspect(data: tuple[bytes, bytes, bytes, str, Ed25519PrivateKey],
            *, pack: bytes | None = None, manifest: bytes | None = None,
            trust: bytes | None = None, pin: str | None = None,
            now: datetime = NOW) -> dict[str, Any]:
    p, m, t, digest, _ = data
    return review_signed_pack(
        pack_bytes=p if pack is None else pack,
        manifest_bytes=m if manifest is None else manifest,
        trust_bytes=t if trust is None else trust,
        expected_key_sha256=digest if pin is None else pin,
        now=now,
    )


def test_valid_review_has_proof_only_of_key_possession(example: Any) -> None:
    report = inspect(example)
    assert report["status"] == "ED25519_VALID_UNDER_CALLER_SUPPLIED_PIN_NO_HOST_SCAN"
    assert report["signature_valid_for_pinned_key"] is True
    assert report["pack_sha256"] == hashlib.sha256(example[0]).hexdigest()
    assert report["external_pinned_key_sha256"] == example[3]
    for flag in (
        "external_key_pin_independently_authenticated_by_phios",
        "publisher_real_world_identity_authenticated",
        "indicator_accuracy_verified", "host_security_observed",
        "scan_performed", "network_access_performed",
        "launch_authority", "gateway_authority",
    ):
        assert report[flag] is False
    assert report["effects_performed"] == []


def test_pack_mutation_rejected(example: Any) -> None:
    with pytest.raises(ValueError, match="digest mismatch"):
        inspect(example, pack=example[0] + b" ")


def test_signature_mutation_rejected(example: Any) -> None:
    item = json.loads(example[1])
    original = bytearray(base64.b64decode(item["signature_b64"]))
    original[0] ^= 1
    item["signature_b64"] = base64.b64encode(original).decode()
    with pytest.raises(ValueError, match="signature invalid"):
        inspect(example, manifest=wire(item))


def test_wrong_external_pin_refused_even_when_signature_valid(example: Any) -> None:
    with pytest.raises(ValueError, match="out-of-band SHA-256 pin"):
        inspect(example, pin="f" * 64)


def test_missing_external_pin_rejected(example: Any) -> None:
    with pytest.raises(ValueError, match="external Ed25519 key"):
        inspect(example, pin="")


def test_unknown_and_revoked_keys_fail(example: Any) -> None:
    trust = json.loads(example[2])
    trust["publishers"] = []
    with pytest.raises(ValueError, match="not in locally supplied"):
        inspect(example, trust=wire(trust))
    trust = json.loads(example[2])
    trust["publishers"][0]["keys"][0]["state"] = "revoked"
    with pytest.raises(ValueError, match="revoked"):
        inspect(example, trust=wire(trust))


def test_blocked_digest_and_issuance_floor(example: Any) -> None:
    trust = json.loads(example[2])
    trust["publishers"][0]["blocked_pack_sha256"] = [hashlib.sha256(example[0]).hexdigest()]
    with pytest.raises(ValueError, match="blocked"):
        inspect(example, trust=wire(trust))
    trust["publishers"][0]["blocked_pack_sha256"] = []
    trust["publishers"][0]["minimum_issued_at"] = "2026-03-01T00:00:00Z"
    with pytest.raises(ValueError, match="predates"):
        inspect(example, trust=wire(trust))


def test_expired_and_not_yet_valid(example: Any) -> None:
    with pytest.raises(ValueError, match="not valid"):
        inspect(example, now=datetime(2027, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="not valid"):
        inspect(example, now=datetime(2025, 12, 1, tzinfo=timezone.utc))


def test_identity_mutation_breaks_signature(example: Any) -> None:
    manifest = json.loads(example[1])
    manifest["publisher"] = "impostor"
    trust = json.loads(example[2])
    trust["publishers"][0]["id"] = "impostor"
    with pytest.raises(ValueError, match="signature invalid"):
        inspect(example, manifest=wire(manifest), trust=wire(trust))


def test_duplicate_properties_and_unknown_manifest_fields_fail(example: Any) -> None:
    duplicate = example[1].replace(b'"publisher":', b'"publisher":"impostor","publisher":', 1)
    with pytest.raises(ValueError, match="strict UTF-8 JSON"):
        inspect(example, manifest=duplicate)
    manifest = json.loads(example[1])
    manifest["execution_authority"] = True
    with pytest.raises(ValueError, match="Malformed"):
        inspect(example, manifest=wire(manifest))


def test_non_pack_signed_payload_rejected_after_signature(example: Any) -> None:
    private = example[4]
    pack = wire({"schema": "something-else", "indicators": []})
    header = json.loads(example[1])
    header["pack_sha256"] = hashlib.sha256(pack).hexdigest()
    header.pop("signature_b64")
    signature = base64.b64encode(private.sign(DOMAIN + wire(header))).decode()
    with pytest.raises(ValueError, match="supported Sentinel IOC pack"):
        inspect(example, pack=pack, manifest=wire({**header, "signature_b64": signature}))


def test_main_refuses_without_operator_approval_and_with_symlink(
    example: Any, tmp_path: Path, capsys: Any,
) -> None:
    pack = tmp_path / "pack.json"
    sig = tmp_path / "manifest.json"
    trust = tmp_path / "trust.json"
    pack.write_bytes(example[0])
    sig.write_bytes(example[1])
    trust.write_bytes(example[2])
    argv = ["--pack", str(pack), "--signature", str(sig), "--trust", str(trust),
            "--expected-public-key-sha256", example[3]]
    assert main(argv) == 2
    assert "Explicit" in capsys.readouterr().err
    assert main([*argv, "--i-approve-local-review"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["host_security_observed"] is False
    symlink = tmp_path / "pack-link.json"
    try:
        symlink.symlink_to(pack)
    except (OSError, NotImplementedError):
        pytest.skip("No symlink support on this platform")
    argv[1] = str(symlink)
    assert main([*argv, "--i-approve-local-review"]) == 2
    assert "Symlink" in capsys.readouterr().err
