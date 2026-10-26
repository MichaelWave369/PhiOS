"""PhiARK R1.6: offline cross-receipt coherence, always held for trusted approval.

Combines *historical*, unsigned receipts from R1.0/R1.1/R1.4/R1.5.
Does not read /proc, connect sockets, execute a child, inspect current
installed bytes, authenticate GitHub, establish freshness or grant authority.
A malicious actor can fabricate internally consistent receipts. This
function is a consistency *diagnostic*, never a launch decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .phiark_service_plan import APP_ID, SOURCE

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MAX_RECEIPT_BYTES = 16384

_SCHEMAS: dict[str, tuple[str, str, str, frozenset[str]]] = {
    "archive": (
        "phios.phiark_archive_chain.v0.1",
        "ARCHIVE_BYTES_MATCHED_LOCAL_RECEIPTS",
        "review_sha256",
        frozenset((
            "schema status app_id repository_url source_commit_claim archive_sha256 "
            "acquisition_tree_sha256 source_snapshot_sha256 installed_tree_sha256 "
            "installed_lineage_review_sha256 source_archive_bytes_matched_local_receipt "
            "acquisition_build_install_crosschecked source_authenticated_against_github "
            "build_toolchain_attested physical_network_isolation_qualified service_supervised "
            "offline_cold_start_verified install_authority launch_authority gateway_authority "
            "review_sha256"
        ).split()),
    ),
    "lineage": (
        "phios.phiark_package_lineage.v0.1",
        "HELD_FOR_SOURCE_ATTESTATION",
        "review_sha256",
        frozenset((
            "schema status app_id source_repository source_commit_claim expected_commit "
            "package_plan_sha256 install_receipt_sha256 installed_tree_sha256 "
            "runtime_preview_sha256 local_package_lineage_consistent source_archive_attested "
            "build_source_lineage_independently_verified toolchain_attested "
            "service_supervision_verified physical_network_isolation_qualified "
            "offline_cold_start_verified install_authority launch_authority gateway_authority "
            "review_sha256"
        ).split()),
    ),
    "peer": (
        "phios.phiark_peer_credential_observation.v0.1",
        "LOCAL_PEER_CREDENTIALS_MATCH_UNQUALIFIED",
        "receipt_sha256",
        frozenset((
            "schema status app_id observation_kind expected_pid peer_pid peer_uid peer_gid "
            "expected_process_start_ticks boot_id peer_pid_uid_equal_expected_process "
            "stable_process_and_socket_observations first_observation_sha256 "
            "second_observation_sha256 stability_comparison_sha256 application_bytes_sent "
            "listener_authenticated_as_phiark source_authenticated_against_github "
            "toolchain_attested network_namespace_verified process_supervision_verified "
            "install_authority launch_authority gateway_authority service_started_or_stopped "
            "receipt_sha256"
        ).split()),
    ),
    "executable": (
        "phios.phiark_process_executable_observation.v0.1",
        "EXECUTABLE_HASH_MATCHES_CALLER_INPUT_UNQUALIFIED",
        "receipt_sha256",
        frozenset((
            "schema status app_id peer_receipt_sha256 pid boot_id pid_start_ticks uid "
            "expected_executable_sha256 observed_executable_sha256 executable_byte_count "
            "linux_process_netns_dev linux_process_netns_inode linux_observer_netns_dev "
            "linux_observer_netns_inode network_namespace_relation "
            "peer_receipt_is_signed_or_fresh executable_pin_independently_authenticated "
            "source_authenticated_against_github network_access_denial_verified "
            "toolchain_attested service_supervision_verified launch_authority "
            "gateway_authority operations_performed receipt_sha256"
        ).split()),
    ),
}
_FALSE = {
    "archive": (
        "source_authenticated_against_github build_toolchain_attested "
        "physical_network_isolation_qualified service_supervised "
        "offline_cold_start_verified install_authority launch_authority gateway_authority"
    ).split(),
    "lineage": (
        "source_archive_attested build_source_lineage_independently_verified "
        "toolchain_attested service_supervision_verified "
        "physical_network_isolation_qualified offline_cold_start_verified "
        "install_authority launch_authority gateway_authority"
    ).split(),
    "peer": (
        "listener_authenticated_as_phiark source_authenticated_against_github "
        "toolchain_attested network_namespace_verified process_supervision_verified "
        "install_authority launch_authority gateway_authority service_started_or_stopped"
    ).split(),
    "executable": (
        "peer_receipt_is_signed_or_fresh executable_pin_independently_authenticated "
        "source_authenticated_against_github network_access_denial_verified "
        "toolchain_attested service_supervision_verified launch_authority gateway_authority"
    ).split(),
}
_BLOCKERS = (
    "independently_authenticated_source_commit",
    "independently_trusted_executable_pin_and_toolchain",
    "fresh_operator_bound_service_launch_and_process_lease",
    "actual_network_access_denial_and_sandbox_qualification",
    "verified_disconnected_cold_start_and_supervision",
    "separately_reviewed_gateway_authorization",
)


def _canonical_hash(record: dict[str, Any]) -> str:
    wire = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(wire.encode("utf-8")) > _MAX_RECEIPT_BYTES:
        raise ValueError("PhiARK evidence record is oversized")
    return hashlib.sha256(wire.encode("utf-8")).hexdigest()


def _hex_digest(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("PhiARK evidence mismatch: " + message)


def _verified_record(value: Any, kind: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("PhiARK evidence receipt must be a mapping: " + kind)
    schema, status, hash_key, exact = _SCHEMAS[kind]
    _require(set(value) == exact, kind + " has missing or unknown fields")
    _require(value["schema"] == schema and value["status"] == status, kind + " schema/status")
    _require(value["app_id"] == APP_ID, kind + " app ID")
    _require(_hex_digest(value[hash_key]), kind + " missing canonical digest")
    body = dict(value)
    body.pop(hash_key)
    try:
        digest = _canonical_hash(body)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("PhiARK evidence has malformed canonical fields: " + kind) from exc
    _require(digest == value[hash_key], kind + " canonical hash")
    for field in _FALSE[kind]:
        _require(value[field] is False, kind + " asserts unsupported " + field)
    return value


def review_phiark_evidence_coherence(
    archive_report_value: Any,
    lineage_report_value: Any,
    peer_report_value: Any,
    executable_report_value: Any,
) -> dict[str, Any]:
    """Reconcile four prior local receipts without I/O or new launch authority."""
    archive = _verified_record(archive_report_value, "archive")
    lineage = _verified_record(lineage_report_value, "lineage")
    peer = _verified_record(peer_report_value, "peer")
    executable = _verified_record(executable_report_value, "executable")

    _require(
        archive["repository_url"] == SOURCE and lineage["source_repository"] == SOURCE,
        "source repository",
    )
    claim = archive["source_commit_claim"]
    _require(
        isinstance(claim, str) and _COMMIT.fullmatch(claim) is not None
        and claim == lineage["source_commit_claim"] == lineage["expected_commit"],
        "source commit claims",
    )
    _require(
        archive["installed_lineage_review_sha256"] == lineage["review_sha256"],
        "archive-to-installed-lineage receipt hash",
    )
    _require(
        _hex_digest(archive["installed_tree_sha256"])
        and archive["installed_tree_sha256"] == lineage["installed_tree_sha256"],
        "installed tree identity",
    )
    for field in (
        "archive_sha256", "acquisition_tree_sha256", "source_snapshot_sha256",
    ):
        _require(_hex_digest(archive[field]), "archive proof " + field)
    for field in (
        "package_plan_sha256", "install_receipt_sha256", "runtime_preview_sha256",
    ):
        _require(_hex_digest(lineage[field]), "lineage proof " + field)
    _require(
        archive["source_archive_bytes_matched_local_receipt"] is True
        and archive["acquisition_build_install_crosschecked"] is True
        and lineage["local_package_lineage_consistent"] is True,
        "local acquisition and installed lineage evidence",
    )
    _require(
        peer["observation_kind"] == "EXPLICIT_AF_UNIX_CONNECT_NO_APPLICATION_PAYLOAD"
        and peer["peer_pid_uid_equal_expected_process"] is True
        and peer["stable_process_and_socket_observations"] is True
        and type(peer["application_bytes_sent"]) is int
        and peer["application_bytes_sent"] == 0,
        "historical local peer observation",
    )
    for field in (
        "first_observation_sha256", "second_observation_sha256",
        "stability_comparison_sha256",
    ):
        _require(_hex_digest(peer[field]), "peer observation hash " + field)
    pid = peer["expected_pid"]
    _require(
        type(pid) is int and 0 < pid <= 4194304
        and type(peer["peer_pid"]) is int and peer["peer_pid"] == pid
        and type(executable["pid"]) is int and executable["pid"] == pid
        and executable["peer_receipt_sha256"] == peer["receipt_sha256"],
        "historical process and peer receipt identity",
    )
    _require(
        type(peer["peer_uid"]) is int and peer["peer_uid"] >= 0
        and type(peer["peer_gid"]) is int and peer["peer_gid"] >= 0
        and type(executable["uid"]) is int and executable["uid"] == peer["peer_uid"]
        and type(peer["expected_process_start_ticks"]) is int
        and peer["expected_process_start_ticks"] > 0
        and type(executable["pid_start_ticks"]) is int
        and executable["pid_start_ticks"] == peer["expected_process_start_ticks"]
        and type(peer["boot_id"]) is str
        and peer["boot_id"] == executable["boot_id"],
        "historical Linux boot, uid or process-start evidence",
    )
    _require(
        _hex_digest(executable["expected_executable_sha256"])
        and executable["observed_executable_sha256"] == executable["expected_executable_sha256"]
        and type(executable["executable_byte_count"]) is int
        and 0 < executable["executable_byte_count"] <= 128 * 1024 * 1024
        and executable["operations_performed"] == [],
        "historical executable observation",
    )
    net_keys = (
        "linux_process_netns_dev", "linux_process_netns_inode",
        "linux_observer_netns_dev", "linux_observer_netns_inode",
    )
    _require(
        all(type(executable[key]) is int and executable[key] >= 0 for key in net_keys),
        "invalid network namespace identifiers",
    )
    shared_ns = (
        executable["linux_process_netns_dev"] == executable["linux_observer_netns_dev"]
        and executable["linux_process_netns_inode"] == executable["linux_observer_netns_inode"]
    )
    _require(
        executable["network_namespace_relation"] == (
            "SAME_AS_OBSERVER" if shared_ns else "DIFFERENT_FROM_OBSERVER_UNQUALIFIED"
        ),
        "contradictory network namespace relation",
    )
    # The prestart R1.0/R1.1 receipts and poststart R1.4/R1.5 receipts are
    # necessarily time-separated. Without a supervised launch nonce/lease,
    # comparing them NEVER proves continuity or service authenticity.
    result: dict[str, Any] = {
        "schema": "phios.phiark_evidence_coherence.v0.1",
        "status": "HELD_FOR_INDEPENDENT_TRUST_AND_LAUNCH_PROOF",
        "app_id": APP_ID,
        "source_commit_claim": claim,
        "installed_tree_sha256": archive["installed_tree_sha256"],
        "archive_review_sha256": archive["review_sha256"],
        "lineage_review_sha256": lineage["review_sha256"],
        "runtime_preview_sha256": lineage["runtime_preview_sha256"],
        "peer_receipt_sha256": peer["receipt_sha256"],
        "process_executable_receipt_sha256": executable["receipt_sha256"],
        "historical_pid": pid,
        "historical_boot_id": peer["boot_id"],
        "historical_pid_start_ticks": peer["expected_process_start_ticks"],
        "historical_executable_sha256": executable["observed_executable_sha256"],
        "historical_network_namespace_relation": executable["network_namespace_relation"],
        "local_cross_receipt_coherence": True,
        "historical_peer_identity_consistent": True,
        "current_process_and_socket_rechecked": False,
        "evidence_temporally_bound_to_approved_launch": False,
        "source_commit_independently_authenticated": False,
        "toolchain_pin_independently_authenticated": False,
        "physical_network_denial_verified": False,
        "real_service_supervision_verified": False,
        "offline_cold_start_verified": False,
        "install_authority": False,
        "launch_authority": False,
        "gateway_authority": False,
        "remaining_blockers": list(_BLOCKERS),
        "operations_performed": [],
    }
    result["review_sha256"] = _canonical_hash(result)
    return result
