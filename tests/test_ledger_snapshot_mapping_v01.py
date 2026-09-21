import json
from pathlib import Path

import pytest

from phios.ledger_reports import LedgerSnapshotExporter
from phios.mandala import AuthorityContext


def _authority() -> AuthorityContext:
    return AuthorityContext(
        ceiling=("ledger.snapshot.export",),
        grants=("ledger.snapshot.export",),
    )


def _write(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def test_gate_authority_and_provenance_are_not_projected(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "gate-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "test",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "GateReceipt",
            "gate": "ACTION",
            "reason": "allowed",
            "provenance_refs": ["/private/path"],
            "authority": {"ceiling": ["secret"], "grants": ["secret"]},
        },
    )
    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())
    row = json.loads(
        (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert row["receipt_type"] == "GateReceipt"
    assert row["reason"] == "allowed"
    assert "authority" not in row
    assert "provenance_refs" not in row


def test_unknown_mandala_receipt_type_rejects_snapshot(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "future-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "future",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "FutureReceipt",
        },
    )
    with pytest.raises(ValueError, match="unknown Mandala receipt_type"):
        LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())


def test_dangling_mandala_parent_is_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "action-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "test",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": "missing-gate",
            "receipt_type": "ActionReceipt",
            "approved_grant": ["artifact.write"],
            "side_effect": {"capability_id": "commons.text_artifact"},
            "outcome": "succeeded",
            "external_identifiers": {"artifact_path": "/secret"},
        },
    )
    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())
    assert snapshot.coverage.complete is False
    assert snapshot.coverage.dangling_parent_receipts == (
        {
            "receipt_id": "action-1",
            "missing_parent_receipt_id": "missing-gate",
        },
    )


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "receipts.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version":"phios.execution_receipt.v0.1",'
        '"schema_version":"phios.execution_receipt.v0.1"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())



def test_reality_projection_includes_bounded_observability_hashes(
    tmp_path: Path,
) -> None:
    frontier_sha = "a" * 64
    observability_sha = "b" * 64
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "reality-frontier-1",
            "packet_id": "packet-frontier-1",
            "task_id": "task-frontier-1",
            "status": "ACCEPTED",
            "produced_by": "reality.verifier",
            "timestamp_utc": "2026-09-21T17:30:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "RealityReceipt",
            "claims_checked": [],
            "evidence_used": [],
            "unresolved_contradictions": [],
            "unresolved_claims": [],
            "verdict_summary": {"SUPPORTED": 1},
            "verification_method": "bounded-evidence-v0.14",
            "promotion_status": "not_promoted",
            "limitations": [],
            "observation_frontier_sha256": frontier_sha,
            "observability_receipt_sha256": observability_sha,
            "observability_status": "BOUNDED",
        },
    )

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority()
    )
    row = json.loads(
        (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )

    assert row["receipt_type"] == "RealityReceipt"
    assert row["observation_frontier_sha256"] == frontier_sha
    assert row["observability_receipt_sha256"] == observability_sha
    assert row["observability_status"] == "BOUNDED"
    assert "authority" not in row


def test_independence_and_disagreement_projection_are_bounded(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger" / "mandala-receipts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "receipt_id": "ind-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "phios.deliberation_evidence",
            "timestamp_utc": "2026-09-21T19:40:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "IndependenceReceipt",
            "claim_id": "claim-1",
            "evidence_paths": [{"secret": "not projected"}],
            "pairwise_relations": [{"basis_refs": ["private"]}],
            "independence_status": "DEPENDENT",
            "independent_pair_count": 0,
            "dependent_pair_count": 1,
            "unknown_pair_count": 0,
            "demonstrated_independent_group_count": 1,
            "dependency_groups": [["a", "b"]],
            "agreement_without_independence": True,
            "assessment_sha256": "a" * 64,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "receipt_sha256": "b" * 64,
        },
        {
            "receipt_id": "dis-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "phios.deliberation_evidence",
            "timestamp_utc": "2026-09-21T19:40:01+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": "ind-1",
            "receipt_type": "DisagreementDecompositionReceipt",
            "claim_id": "claim-1",
            "independence_receipt_sha256": "b" * 64,
            "stance_counts": {"SUPPORTS": 2, "CONTRADICTS": 0, "UNCERTAIN": 0},
            "independent_stance_group_counts": {
                "SUPPORTS": 1,
                "CONTRADICTS": 0,
                "UNCERTAIN": 0,
            },
            "contested_group_count": 0,
            "dependency_groups": [{"path_ids": ["a", "b"], "stances": ["SUPPORTS"]}],
            "disagreement_status": "UNANIMOUS_PARTICIPANTS",
            "independence_qualified_agreement": False,
            "consensus_authority": False,
            "promotion_status": "not_promoted",
            "assessment_sha256": "c" * 64,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "receipt_sha256": "d" * 64,
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority()
    )
    projected = [
        json.loads(line)
        for line in (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert projected[0]["receipt_type"] == "IndependenceReceipt"
    assert projected[0]["demonstrated_independent_group_count"] == 1
    assert projected[0]["agreement_without_independence"] is True
    assert "evidence_paths" not in projected[0]
    assert "pairwise_relations" not in projected[0]
    assert projected[1]["receipt_type"] == "DisagreementDecompositionReceipt"
    assert projected[1]["independence_qualified_agreement"] is False
    assert projected[1]["consensus_authority"] is False
    assert projected[1]["promotion_status"] == "not_promoted"
    assert "stance_counts" not in projected[1]
    assert "dependency_groups" not in projected[1]


def test_governance_escalation_projection_is_bounded(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger" / "mandala-receipts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "receipt_id": "verifier-semantics-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "phios.verifier_semantics",
            "timestamp_utc": "2026-09-21T20:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": "reality-1",
            "receipt_type": "VerifierSemanticsReceipt",
            "source_reality_receipt_id": "reality-1",
            "semantics_schema_version": "phios.verifier_semantics.v0.1",
            "source_reality_receipt_sha256": "a" * 64,
            "verifier_id": "reality.verifier",
            "verification_method": "bounded-evidence-v0.14",
            "source_status": "DISPUTED",
            "observation_frontier_sha256": "f" * 64,
            "observability_receipt_sha256": "1" * 64,
            "observability_status": "BOUNDED",
            "verdict_summary": {"CONTRADICTED": 1},
            "detects_evidence_state": True,
            "may_emit_escalation_request": True,
            "may_authorize_remediation": False,
            "may_execute_remediation": False,
            "may_promote": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "receipt_sha256": "b" * 64,
        },
        {
            "receipt_id": "escalation-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "phios.governance_escalation",
            "timestamp_utc": "2026-09-21T20:00:01+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": "verifier-semantics-1",
            "receipt_type": "GovernanceEscalationReceipt",
            "source_reality_receipt_id": "reality-1",
            "escalation_schema_version": "phios.governance_escalation.v0.1",
            "source_reality_receipt_sha256": "a" * 64,
            "verifier_semantics_receipt_sha256": "b" * 64,
            "request_id": "request-1",
            "disposition": "REMEDIATE",
            "routing_status": "ROUTED_FOR_AUTHORIZATION",
            "reason": "private detailed remediation reason",
            "target_ref": "governed_action_binding.review",
            "trigger_claim_ids": ["claim-secret-1"],
            "trigger_verdicts": [
                {"claim_id": "claim-secret-1", "verdict": "CONTRADICTED"}
            ],
            "candidate_capability_id": "commons.text_artifact",
            "candidate_capability_version": "0.1.0",
            "candidate_capability_risk": "low",
            "candidate_capability_contract_sha256": "c" * 64,
            "candidate_payload_sha256": "d" * 64,
            "requested_permissions": ["artifact.write"],
            "requested_effects": ["filesystem.change"],
            "downstream_authority_required": True,
            "remediation_authorized": False,
            "remediation_executed": False,
            "promotion_status": "not_promoted",
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
            "receipt_sha256": "e" * 64,
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority()
    )
    projected = [
        json.loads(line)
        for line in (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    semantics = projected[0]
    escalation = projected[1]
    assert semantics["receipt_type"] == "VerifierSemanticsReceipt"
    assert semantics["may_authorize_remediation"] is False
    assert semantics["may_execute_remediation"] is False
    assert semantics["observability_status"] == "BOUNDED"
    assert semantics["observation_frontier_sha256"] == "f" * 64
    assert semantics["action_authority"] is False
    assert escalation["receipt_type"] == "GovernanceEscalationReceipt"
    assert escalation["routing_status"] == "ROUTED_FOR_AUTHORIZATION"
    assert escalation["trigger_claim_count"] == 1
    assert escalation["requested_permission_count"] == 1
    assert escalation["requested_effect_count"] == 1
    assert escalation["remediation_authorized"] is False
    assert escalation["remediation_executed"] is False
    assert escalation["action_authority"] is False
    assert "reason" not in escalation
    assert "trigger_claim_ids" not in escalation
    assert "trigger_verdicts" not in escalation
    assert "requested_permissions" not in escalation
    assert "requested_effects" not in escalation
