"""PhiARK R1.6 historical evidence join, rejection and non-authority tests."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from phios.apps.phiark_evidence_coherence import (
    _FALSE,
    _SCHEMAS,
    review_phiark_evidence_coherence,
)

_APP = "phi.phiark"
_REPO = "https://github.com/MichaelWave369/PhiARK"
_COMMIT = "d0c01e7200d07ae4c5448375878e5188048a6a40"


def _digest(fields: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _record(kind: str, **overrides: Any) -> dict[str, Any]:
    schema, status, key, required = _SCHEMAS[kind]
    body: dict[str, Any] = dict.fromkeys(required - {key})
    body.update(schema=schema, status=status, app_id=_APP)
    body.update({name: False for name in _FALSE[kind]})
    body.update(overrides)
    assert set(body) == required - {key}
    assert all(value is not None for value in body.values())
    body[key] = _digest(body)
    return body


def _recompute(kind: str, record: dict[str, Any], **updates: Any) -> dict[str, Any]:
    result = {**record, **updates}
    key = _SCHEMAS[kind][2]
    result.pop(key)
    result[key] = _digest(result)
    return result


def _samples() -> tuple[dict, dict, dict, dict]:
    lineage = _record(
        "lineage",
        source_repository=_REPO,
        source_commit_claim=_COMMIT,
        expected_commit=_COMMIT,
        package_plan_sha256="1" * 64,
        install_receipt_sha256="2" * 64,
        installed_tree_sha256="3" * 64,
        runtime_preview_sha256="4" * 64,
        local_package_lineage_consistent=True,
    )
    archive = _record(
        "archive",
        repository_url=_REPO,
        source_commit_claim=_COMMIT,
        archive_sha256="5" * 64,
        acquisition_tree_sha256="6" * 64,
        source_snapshot_sha256="7" * 64,
        installed_tree_sha256="3" * 64,
        installed_lineage_review_sha256=lineage["review_sha256"],
        source_archive_bytes_matched_local_receipt=True,
        acquisition_build_install_crosschecked=True,
    )
    peer = _record(
        "peer",
        observation_kind="EXPLICIT_AF_UNIX_CONNECT_NO_APPLICATION_PAYLOAD",
        expected_pid=31415,
        peer_pid=31415,
        peer_uid=1000,
        peer_gid=1000,
        expected_process_start_ticks=87329,
        boot_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        peer_pid_uid_equal_expected_process=True,
        stable_process_and_socket_observations=True,
        first_observation_sha256="8" * 64,
        second_observation_sha256="9" * 64,
        stability_comparison_sha256="a" * 64,
        application_bytes_sent=0,
    )
    executable = _record(
        "executable",
        peer_receipt_sha256=peer["receipt_sha256"],
        pid=31415,
        boot_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        pid_start_ticks=87329,
        uid=1000,
        expected_executable_sha256="b" * 64,
        observed_executable_sha256="b" * 64,
        executable_byte_count=4096,
        linux_process_netns_dev=4,
        linux_process_netns_inode=100,
        linux_observer_netns_dev=4,
        linux_observer_netns_inode=200,
        network_namespace_relation="DIFFERENT_FROM_OBSERVER_UNQUALIFIED",
        operations_performed=[],
    )
    return archive, lineage, peer, executable


def test_cross_receipt_join_reconciles_historical_evidence_but_stays_held() -> None:
    archive, lineage, peer, executable = _samples()
    result = review_phiark_evidence_coherence(archive, lineage, peer, executable)
    assert result["status"] == "HELD_FOR_INDEPENDENT_TRUST_AND_LAUNCH_PROOF"
    assert result["source_commit_claim"] == _COMMIT
    assert result["installed_tree_sha256"] == "3" * 64
    assert result["peer_receipt_sha256"] == peer["receipt_sha256"]
    assert result["process_executable_receipt_sha256"] == executable["receipt_sha256"]
    assert result["historical_pid"] == peer["expected_pid"]
    assert result["historical_network_namespace_relation"] == "DIFFERENT_FROM_OBSERVER_UNQUALIFIED"
    assert result["local_cross_receipt_coherence"] is True
    assert result["historical_peer_identity_consistent"] is True
    assert result["evidence_temporally_bound_to_approved_launch"] is False
    assert result["current_process_and_socket_rechecked"] is False
    assert result["source_commit_independently_authenticated"] is False
    assert result["physical_network_denial_verified"] is False
    assert result["real_service_supervision_verified"] is False
    assert result["install_authority"] is False
    assert result["launch_authority"] is False
    assert result["gateway_authority"] is False
    assert result["operations_performed"] == []
    assert len(result["remaining_blockers"]) == 6
    unsigned = dict(result)
    assert unsigned.pop("review_sha256") == _digest(unsigned)
    assert result == review_phiark_evidence_coherence(archive, lineage, peer, executable)


@pytest.mark.parametrize("kind,index,update,problem", [
    ("archive", 0, {"installed_tree_sha256": "d" * 64}, "installed tree identity"),
    ("archive", 0, {"source_commit_claim": "f" * 40}, "source commit claims"),
    ("lineage", 1, {"expected_commit": "f" * 40}, "source commit claims"),
    ("peer", 2, {"peer_pid": 31416}, "historical process and peer receipt identity"),
    ("peer", 2, {"boot_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}, "historical Linux"),
    ("executable", 3, {"uid": 1500}, "historical Linux"),
    ("executable", 3, {"pid_start_ticks": 12}, "historical Linux"),
    ("executable", 3, {"expected_executable_sha256": "d" * 64}, "historical executable"),
    ("executable", 3, {"network_namespace_relation": "SAME_AS_OBSERVER"}, "contradictory network"),
])
def test_canonical_but_conflicting_evidence_is_rejected(
    kind: str, index: int, update: dict[str, Any], problem: str,
) -> None:
    evidence = list(_samples())
    evidence[index] = _recompute(kind, evidence[index], **update)
    if kind == "peer" and "boot_id" in update:
        # Rebind the executable to the changed peer receipt so the test
        # reaches the *boot ID* comparison instead of failing earlier on
        # the intentionally stale peer_receipt_sha256 integrity link.
        evidence[3] = _recompute(
            "executable", evidence[3],
            peer_receipt_sha256=evidence[2]["receipt_sha256"],
        )
    with pytest.raises(ValueError, match=problem):
        review_phiark_evidence_coherence(*evidence)


@pytest.mark.parametrize("kind,index,field", [
    ("archive", 0, "launch_authority"),
    ("archive", 0, "build_toolchain_attested"),
    ("lineage", 1, "source_archive_attested"),
    ("lineage", 1, "toolchain_attested"),
    ("peer", 2, "listener_authenticated_as_phiark"),
    ("peer", 2, "gateway_authority"),
    ("executable", 3, "network_access_denial_verified"),
    ("executable", 3, "executable_pin_independently_authenticated"),
])
def test_rehashed_authority_assertion_is_rejected(
    kind: str, index: int, field: str,
) -> None:
    evidence = list(_samples())
    evidence[index] = _recompute(kind, evidence[index], **{field: True})
    with pytest.raises(ValueError, match="asserts unsupported"):
        review_phiark_evidence_coherence(*evidence)


def test_unrecomputed_tampering_unknown_fields_and_wrong_schema_rejected() -> None:
    a, l, p, e = _samples()
    with pytest.raises(ValueError, match="canonical hash"):
        review_phiark_evidence_coherence({**a, "source_commit_claim": "f" * 40}, l, p, e)
    with pytest.raises(ValueError, match="missing or unknown"):
        review_phiark_evidence_coherence({**a, "grant": "launch"}, l, p, e)
    with pytest.raises(ValueError, match="schema/status"):
        review_phiark_evidence_coherence(_recompute("archive", a, status="READY"), l, p, e)
    with pytest.raises(ValueError, match="must be a mapping"):
        review_phiark_evidence_coherence(None, l, p, e)
    with pytest.raises(ValueError, match="canonical hash"):
        review_phiark_evidence_coherence(a, l, {**p, "peer_pid": 43}, e)


def test_peer_and_executable_must_be_linked_to_same_receipt() -> None:
    a, l, p, e = _samples()
    altered_peer = _recompute("peer", p, expected_pid=12345, peer_pid=12345)
    with pytest.raises(ValueError, match="historical process"):
        review_phiark_evidence_coherence(a, l, altered_peer, e)
    stale_executable = _recompute(
        "executable", e, peer_receipt_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="historical process"):
        review_phiark_evidence_coherence(a, l, p, stale_executable)


def test_network_namespace_same_relation_is_informational_not_qualification() -> None:
    a, l, p, e = _samples()
    same_ns = _recompute(
        "executable", e,
        linux_observer_netns_dev=4, linux_observer_netns_inode=100,
        network_namespace_relation="SAME_AS_OBSERVER",
    )
    out = review_phiark_evidence_coherence(a, l, p, same_ns)
    assert out["historical_network_namespace_relation"] == "SAME_AS_OBSERVER"
    assert out["physical_network_denial_verified"] is False
    assert out["launch_authority"] is False


def test_untrusted_self_consistent_receipts_never_become_signed_evidence() -> None:
    # Even knowing all hashes and supplying perfectly consistent records isn't
    # proof of GitHub or a reviewed one-shot runtime session.
    a, l, p, e = _samples()
    joined = review_phiark_evidence_coherence(a, l, p, e)
    assert "independently_authenticated_source_commit" in joined["remaining_blockers"]
    assert "fresh_operator_bound_service_launch_and_process_lease" in joined["remaining_blockers"]
    assert joined["status"].startswith("HELD_FOR_")
