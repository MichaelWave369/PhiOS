"""PhiARK R1.7: offline publisher-statement signature verification, no launch grant.

A signature proves control of the private key paired with an *externally*
reviewed public key. The caller provides that trust root; neither GitHub nor
PhiOS itself authenticates its provenance. This module never generates keys,
signs software, reads a trust store, inspects current files, or runs a service.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any

from .phiark_evidence_coherence import _SCHEMAS
from .phiark_service_plan import APP_ID, SOURCE

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_KEYID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_DOMAIN = b"PhiOS/PhiARK/source-toolchain-statement/v1\x00"
_MAX_JSON = 16384
_STATEMENT_KEYS = frozenset((
    "schema app_id repository_url commit_sha publisher_key_id profile "
    "source_archive_sha256 installed_tree_sha256 runtime_preview_sha256 "
    "coherence_review_sha256 node_executable_sha256 bubblewrap_pin_sha256 "
    "prlimit_pin_sha256"
).split())
_COHERENCE_KEYS = frozenset((
    "schema status app_id source_commit_claim installed_tree_sha256 "
    "archive_review_sha256 lineage_review_sha256 runtime_preview_sha256 "
    "peer_receipt_sha256 process_executable_receipt_sha256 historical_pid "
    "historical_boot_id historical_pid_start_ticks historical_executable_sha256 "
    "historical_network_namespace_relation local_cross_receipt_coherence "
    "historical_peer_identity_consistent current_process_and_socket_rechecked "
    "evidence_temporally_bound_to_approved_launch "
    "source_commit_independently_authenticated toolchain_pin_independently_authenticated "
    "physical_network_denial_verified real_service_supervision_verified "
    "offline_cold_start_verified install_authority launch_authority gateway_authority "
    "remaining_blockers operations_performed review_sha256"
).split())


def _json(value: dict[str, Any]) -> bytes:
    try:
        wire = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("PhiARK signed pin statement has invalid JSON") from exc
    if len(wire) > _MAX_JSON:
        raise ValueError("PhiARK signed pin statement exceeds size bound")
    return wire


def _hash_without(record: dict[str, Any], field: str) -> str:
    body = dict(record)
    body.pop(field)
    return hashlib.sha256(_json(body)).hexdigest()


def _required(value: bool, problem: str) -> None:
    if not value:
        raise ValueError("PhiARK signed pin review rejected: " + problem)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _previous_reports(
    archive: Any, coherence: Any, executable: Any,
) -> None:
    for label, value in (
        ("archive", archive), ("coherence", coherence), ("executable", executable),
    ):
        _required(type(value) is dict, label + " report required")
        _required(value.get("app_id") == APP_ID, label + " app identity")
    _required(
        set(archive) == _SCHEMAS["archive"][3]
        and archive.get("schema") == "phios.phiark_archive_chain.v0.1"
        and archive.get("status") == "ARCHIVE_BYTES_MATCHED_LOCAL_RECEIPTS"
        and archive.get("repository_url") == SOURCE
        and _sha(archive.get("review_sha256"))
        and archive["review_sha256"] == _hash_without(archive, "review_sha256")
        and archive.get("source_archive_bytes_matched_local_receipt") is True
        and archive.get("acquisition_build_install_crosschecked") is True
        and archive.get("source_authenticated_against_github") is False
        and archive.get("launch_authority") is False
        and archive.get("gateway_authority") is False,
        "prior archive receipt or unsupported authority",
    )
    _required(
        set(coherence) == _COHERENCE_KEYS
        and coherence.get("schema") == "phios.phiark_evidence_coherence.v0.1"
        and coherence.get("status") == "HELD_FOR_INDEPENDENT_TRUST_AND_LAUNCH_PROOF"
        and _sha(coherence.get("review_sha256"))
        and coherence["review_sha256"] == _hash_without(coherence, "review_sha256")
        and coherence.get("local_cross_receipt_coherence") is True
        and coherence.get("historical_peer_identity_consistent") is True
        and coherence.get("archive_review_sha256") == archive["review_sha256"]
        and coherence.get("current_process_and_socket_rechecked") is False
        and coherence.get("evidence_temporally_bound_to_approved_launch") is False
        and coherence.get("source_commit_independently_authenticated") is False
        and coherence.get("toolchain_pin_independently_authenticated") is False
        and coherence.get("physical_network_denial_verified") is False
        and coherence.get("real_service_supervision_verified") is False
        and coherence.get("offline_cold_start_verified") is False
        and coherence.get("install_authority") is False
        and coherence.get("launch_authority") is False
        and coherence.get("gateway_authority") is False
        and coherence.get("operations_performed") == [],
        "prior evidence coherence receipt or unsupported authority",
    )
    _required(
        set(executable) == _SCHEMAS["executable"][3]
        and executable.get("schema") == "phios.phiark_process_executable_observation.v0.1"
        and executable.get("status") == "EXECUTABLE_HASH_MATCHES_CALLER_INPUT_UNQUALIFIED"
        and _sha(executable.get("receipt_sha256"))
        and executable["receipt_sha256"] == _hash_without(executable, "receipt_sha256")
        and executable.get("observed_executable_sha256")
        == executable.get("expected_executable_sha256")
        and executable.get("source_authenticated_against_github") is False
        and executable.get("executable_pin_independently_authenticated") is False
        and executable.get("network_access_denial_verified") is False
        and executable.get("launch_authority") is False
        and executable.get("gateway_authority") is False
        and executable.get("operations_performed") == []
        and executable["receipt_sha256"] ==
        coherence["process_executable_receipt_sha256"],
        "prior executable receipt or unsupported authority",
    )


def verify_phiark_offline_signed_pins(
    *, statement: Any, signature_b64: str,
    pinned_publisher_public_key: bytes, pinned_publisher_key_sha256: str,
    pinned_publisher_key_id: str,
    archive_report: dict[str, Any],
    coherence_report: dict[str, Any],
    executable_report: dict[str, Any],
) -> dict[str, Any]:
    """Verify an Ed25519 statement under a caller-supplied out-of-band key pin.

    A verification result is an informational HOLD, not source identity,
    release readiness, trust-store enrollment or execution authorization.
    """
    if type(statement) is not dict or set(statement) != _STATEMENT_KEYS:
        raise ValueError("PhiARK signed pin statement has missing or unknown fields")
    _required(
        statement.get("schema") == "phios.phiark_offline_publisher_statement.v0.1"
        and statement.get("app_id") == APP_ID
        and statement.get("repository_url") == SOURCE
        and statement.get("profile") == "offline-network-denied"
        and isinstance(statement.get("commit_sha"), str)
        and _SHA40.fullmatch(statement["commit_sha"]) is not None,
        "publisher statement identity or offline profile",
    )
    for key in (
        "source_archive_sha256", "installed_tree_sha256", "runtime_preview_sha256",
        "coherence_review_sha256", "node_executable_sha256", "bubblewrap_pin_sha256",
        "prlimit_pin_sha256",
    ):
        _required(_sha(statement[key]), "malformed " + key)
    _required(
        type(pinned_publisher_key_id) is str
        and _KEYID.fullmatch(pinned_publisher_key_id) is not None
        and statement["publisher_key_id"] == pinned_publisher_key_id,
        "publisher key ID does not match external pin",
    )
    _required(
        type(pinned_publisher_public_key) is bytes
        and len(pinned_publisher_public_key) == 32
        and _sha(pinned_publisher_key_sha256)
        and hashlib.sha256(pinned_publisher_public_key).hexdigest()
        == pinned_publisher_key_sha256,
        "external Ed25519 public-key fingerprint mismatch",
    )
    if not isinstance(signature_b64, str) or len(signature_b64) > 100:
        raise ValueError("PhiARK signed pin signature is not canonical base64")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("PhiARK signed pin signature is not canonical base64") from exc
    if len(signature) != 64 or base64.b64encode(signature).decode() != signature_b64:
        raise ValueError("PhiARK signed pin signature must be canonical Ed25519 bytes")

    # Check historical receipt agreement prior to cryptographic verification.
    _previous_reports(archive_report, coherence_report, executable_report)
    _required(
        archive_report.get("source_commit_claim") == statement["commit_sha"]
        and coherence_report.get("source_commit_claim") == statement["commit_sha"]
        and archive_report.get("archive_sha256") == statement["source_archive_sha256"]
        and archive_report.get("installed_tree_sha256") == statement["installed_tree_sha256"]
        and coherence_report.get("installed_tree_sha256") == statement["installed_tree_sha256"]
        and coherence_report.get("runtime_preview_sha256") == statement["runtime_preview_sha256"]
        and coherence_report.get("review_sha256") == statement["coherence_review_sha256"]
        and coherence_report.get("historical_executable_sha256") == statement["node_executable_sha256"]
        and executable_report.get("observed_executable_sha256") == statement["node_executable_sha256"],
        "publisher pins do not match historical evidence",
    )
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ValueError("PhiARK signature verification requires the cryptography backend") from exc
    try:
        Ed25519PublicKey.from_public_bytes(pinned_publisher_public_key).verify(
            signature, _DOMAIN + _json(statement)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("PhiARK Ed25519 signature does not match externally pinned key") from exc

    report: dict[str, Any] = {
        "schema": "phios.phiark_offline_signed_pin_review.v0.1",
        "status": "SIGNATURE_VALID_UNDER_CALLER_SUPPLIED_PIN_STILL_HELD",
        "app_id": APP_ID,
        "publisher_key_id": pinned_publisher_key_id,
        "publisher_public_key_sha256": pinned_publisher_key_sha256,
        "statement_sha256": hashlib.sha256(_json(statement)).hexdigest(),
        "coherence_review_sha256": coherence_report["review_sha256"],
        "ed25519_signature_valid_for_supplied_public_key": True,
        "publisher_key_provenance_independently_verified": False,
        "github_source_commit_independently_authenticated": False,
        "node_toolchain_pin_authenticated_to_installed_host": False,
        "bubblewrap_pin_authenticated_to_installed_host": False,
        "prlimit_pin_authenticated_to_installed_host": False,
        "historical_process_tied_to_operator_approved_launch": False,
        "network_access_denial_verified": False,
        "offline_cold_start_verified": False,
        "launch_authority": False,
        "gateway_authority": False,
        "operations_performed": [],
    }
    report["review_sha256"] = _hash_without({**report, "review_sha256": ""}, "review_sha256")
    return report
