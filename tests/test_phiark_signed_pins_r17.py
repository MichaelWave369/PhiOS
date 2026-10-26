"""PhiARK R1.7 offline Ed25519 publisher pin verification regression tests."""
from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phios.apps.phiark_evidence_coherence import review_phiark_evidence_coherence
from phios.apps.phiark_signed_pins import (
    _DOMAIN, _json, verify_phiark_offline_signed_pins,
)
from test_phiark_evidence_coherence_r16 import _samples


def _case() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any],
                     dict[str, Any], Ed25519PrivateKey, bytes, str]:
    archive, lineage, peer, executable = _samples()
    coherence = review_phiark_evidence_coherence(archive, lineage, peer, executable)
    key = Ed25519PrivateKey.generate()  # Ephemeral test key only; never a publisher key.
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    statement: dict[str, Any] = {
        "schema": "phios.phiark_offline_publisher_statement.v0.1",
        "app_id": "phi.phiark",
        "repository_url": "https://github.com/MichaelWave369/PhiARK",
        "commit_sha": archive["source_commit_claim"],
        "publisher_key_id": "reviewer-lab",
        "profile": "offline-network-denied",
        "source_archive_sha256": archive["archive_sha256"],
        "installed_tree_sha256": archive["installed_tree_sha256"],
        "runtime_preview_sha256": coherence["runtime_preview_sha256"],
        "coherence_review_sha256": coherence["review_sha256"],
        "node_executable_sha256": executable["observed_executable_sha256"],
        "bubblewrap_pin_sha256": "c" * 64,
        "prlimit_pin_sha256": "d" * 64,
    }
    signature = base64.b64encode(key.sign(_DOMAIN + _json(statement))).decode("ascii")
    return statement, archive, coherence, executable, key, public, signature


def _verify(*, changed: dict[str, Any] | None = None, key: bytes | None = None,
            pin: str | None = None, signature: str | None = None,
            archive_changed: dict[str, Any] | None = None,
            coherence_changed: dict[str, Any] | None = None,
            executable_changed: dict[str, Any] | None = None) -> dict[str, Any]:
    statement, archive, coherence, executable, _, public, wire = _case()
    return verify_phiark_offline_signed_pins(
        statement=changed if changed is not None else statement,
        signature_b64=signature if signature is not None else wire,
        pinned_publisher_public_key=key if key is not None else public,
        pinned_publisher_key_sha256=pin if pin is not None else hashlib.sha256(public).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
        archive_report=archive_changed if archive_changed is not None else archive,
        coherence_report=coherence_changed if coherence_changed is not None else coherence,
        executable_report=executable_changed if executable_changed is not None else executable,
    )


def test_valid_signed_pin_statement_still_holds_without_launch_approval() -> None:
    statement, archive, coherence, executable, _, public, signature = _case()
    result = verify_phiark_offline_signed_pins(
        statement=statement, signature_b64=signature,
        pinned_publisher_public_key=public,
        pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
        archive_report=archive, coherence_report=coherence, executable_report=executable,
    )
    assert result["status"] == "SIGNATURE_VALID_UNDER_CALLER_SUPPLIED_PIN_STILL_HELD"
    assert result["ed25519_signature_valid_for_supplied_public_key"] is True
    assert result["coherence_review_sha256"] == coherence["review_sha256"]
    assert result["publisher_key_provenance_independently_verified"] is False
    assert result["github_source_commit_independently_authenticated"] is False
    assert result["node_toolchain_pin_authenticated_to_installed_host"] is False
    assert result["bubblewrap_pin_authenticated_to_installed_host"] is False
    assert result["prlimit_pin_authenticated_to_installed_host"] is False
    assert result["historical_process_tied_to_operator_approved_launch"] is False
    assert result["network_access_denial_verified"] is False
    assert result["launch_authority"] is False
    assert result["gateway_authority"] is False
    assert result["operations_performed"] == []
    fields = dict(result)
    expected = fields.pop("review_sha256")
    assert hashlib.sha256(_json(fields)).hexdigest() == expected


def test_changed_signed_binary_pin_is_rejected_even_when_syntax_is_valid() -> None:
    statement, archive, coherence, executable, key, public, signature = _case()
    altered = {**statement, "bubblewrap_pin_sha256": "e" * 64}
    with pytest.raises(ValueError, match="signature does not match"):
        verify_phiark_offline_signed_pins(
            statement=altered, signature_b64=signature, pinned_publisher_public_key=public,
            pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
            pinned_publisher_key_id="reviewer-lab",
            archive_report=archive, coherence_report=coherence,
            executable_report=executable,
        )
    # The test private key can re-sign its own changed statement; even then the
    # verifier only reports key possession, never who approved the key.
    fresh_sig = base64.b64encode(key.sign(_DOMAIN + _json(altered))).decode("ascii")
    signed = verify_phiark_offline_signed_pins(
        statement=altered, signature_b64=fresh_sig, pinned_publisher_public_key=public,
        pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
        archive_report=archive, coherence_report=coherence,
        executable_report=executable,
    )
    assert signed["launch_authority"] is False
    assert signed["publisher_key_provenance_independently_verified"] is False


def test_wrong_key_and_external_fingerprint_rejected() -> None:
    statement, archive, coherence, executable, _, public, signature = _case()
    stranger = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    with pytest.raises(ValueError, match="signature does not match"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64=signature,
            pinned_publisher_public_key=stranger,
            pinned_publisher_key_sha256=hashlib.sha256(stranger).hexdigest(),
            pinned_publisher_key_id="reviewer-lab",
            archive_report=archive, coherence_report=coherence, executable_report=executable,
        )
    with pytest.raises(ValueError, match="public-key fingerprint mismatch"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64=signature,
            pinned_publisher_public_key=public,
            pinned_publisher_key_sha256="0" * 64,
            pinned_publisher_key_id="reviewer-lab",
            archive_report=archive, coherence_report=coherence, executable_report=executable,
        )
    with pytest.raises(ValueError, match="key ID"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64=signature,
            pinned_publisher_public_key=public,
            pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
            pinned_publisher_key_id="different-reviewer",
            archive_report=archive, coherence_report=coherence, executable_report=executable,
        )


@pytest.mark.parametrize("field,wrong", [
    ("commit_sha", "f" * 40),
    ("source_archive_sha256", "e" * 64),
    ("installed_tree_sha256", "e" * 64),
    ("coherence_review_sha256", "e" * 64),
    ("node_executable_sha256", "e" * 64),
    ("runtime_preview_sha256", "e" * 64),
])
def test_even_resigned_contradictory_statement_cannot_match_history(
    field: str, wrong: str,
) -> None:
    statement, archive, coherence, executable, private, public, _ = _case()
    changed = {**statement, field: wrong}
    signature = base64.b64encode(private.sign(_DOMAIN + _json(changed))).decode()
    with pytest.raises(ValueError, match="publisher pins do not match"):
        verify_phiark_offline_signed_pins(
            statement=changed, signature_b64=signature,
            pinned_publisher_public_key=public,
            pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
            pinned_publisher_key_id="reviewer-lab",
            archive_report=archive, coherence_report=coherence, executable_report=executable,
        )


def test_reject_unrecognized_fields_bad_signature_and_profile() -> None:
    statement, archive, coherence, executable, _, public, signature = _case()
    kw = dict(
        pinned_publisher_public_key=public,
        pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
        archive_report=archive, coherence_report=coherence, executable_report=executable,
    )
    with pytest.raises(ValueError, match="missing or unknown"):
        verify_phiark_offline_signed_pins(
            statement={**statement, "launch_authority": True}, signature_b64=signature, **kw,
        )
    with pytest.raises(ValueError, match="offline profile"):
        verify_phiark_offline_signed_pins(
            statement={**statement, "profile": "host-network"}, signature_b64=signature, **kw,
        )
    with pytest.raises(ValueError, match="canonical base64"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64="%%%%", **kw,
        )
    with pytest.raises(ValueError, match="canonical Ed25519"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64=base64.b64encode(b"short").decode(), **kw,
        )


def test_hash_rewrites_cannot_promote_prior_coherence_authority() -> None:
    statement, archive, coherence, executable, _, public, signature = _case()
    forged = {**coherence, "launch_authority": True}
    forged.pop("review_sha256")
    forged["review_sha256"] = hashlib.sha256(_json(forged)).hexdigest()
    with pytest.raises(ValueError, match="prior evidence coherence"):
        verify_phiark_offline_signed_pins(
            statement=statement, signature_b64=signature,
            pinned_publisher_public_key=public,
            pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
            pinned_publisher_key_id="reviewer-lab",
            archive_report=archive, coherence_report=forged, executable_report=executable,
        )


def test_declared_pins_never_trigger_binary_checks_or_new_subprocesses() -> None:
    # The module never executes or reads a Node/Bubblewrap/prlimit binary.
    statement, archive, coherence, executable, _, public, signature = _case()
    statement["bubblewrap_pin_sha256"] = "a" * 64
    # Valid re-signing is intentionally possible with a key supplied by the
    # caller: this is *not* an approved/reviewed root of trust.
    signer = Ed25519PrivateKey.generate()
    replacement_key = signer.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    new_signature = base64.b64encode(signer.sign(_DOMAIN + _json(statement))).decode()
    result = verify_phiark_offline_signed_pins(
        statement=statement, signature_b64=new_signature,
        pinned_publisher_public_key=replacement_key,
        pinned_publisher_key_sha256=hashlib.sha256(replacement_key).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
        archive_report=archive, coherence_report=coherence, executable_report=executable,
    )
    assert result["bubblewrap_pin_authenticated_to_installed_host"] is False
    assert result["launch_authority"] is False

def test_extra_fields_in_historical_receipts_are_rejected_even_if_rehashed() -> None:
    statement, archive, coherence, executable, _, public, signature = _case()
    args = dict(
        statement=statement, signature_b64=signature,
        pinned_publisher_public_key=public,
        pinned_publisher_key_sha256=hashlib.sha256(public).hexdigest(),
        pinned_publisher_key_id="reviewer-lab",
    )
    changed_archive = {**archive, "unauthorized_launch_note": True}
    changed_archive.pop("review_sha256")
    changed_archive["review_sha256"] = hashlib.sha256(_json(changed_archive)).hexdigest()
    with pytest.raises(ValueError, match="prior archive"):
        verify_phiark_offline_signed_pins(
            **args, archive_report=changed_archive,
            coherence_report=coherence, executable_report=executable,
        )
    changed_executable = {**executable, "claimed_supervised": True}
    changed_executable.pop("receipt_sha256")
    changed_executable["receipt_sha256"] = hashlib.sha256(_json(changed_executable)).hexdigest()
    with pytest.raises(ValueError, match="prior executable"):
        verify_phiark_offline_signed_pins(
            **args, archive_report=archive, coherence_report=coherence,
            executable_report=changed_executable,
        )
