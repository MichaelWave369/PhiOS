from __future__ import annotations

from pathlib import Path

import pytest

from phios.mandala import AuthorityContext
from phios.memory import (
    EmbeddingIdentity,
    EvidenceHorizonPolicy,
    MemoryAccessPolicy,
    MemoryEvidenceHorizon,
    MemoryPolicyRule,
    MemoryRecord,
    MemoryStore,
    GovernedMemoryService,
    VectorCandidate,
    memory_record_ref,
)


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(
        ceiling=tuple(permissions),
        grants=tuple(permissions),
    )


def _policy() -> MemoryAccessPolicy:
    return MemoryAccessPolicy(
        (
            MemoryPolicyRule(
                principal_id="operator",
                scopes=("private",),
                classifications=("operator",),
            ),
        )
    )


def _horizon() -> MemoryEvidenceHorizon:
    return MemoryEvidenceHorizon(
        EvidenceHorizonPolicy(
            policy_id="test-horizon",
            active_window_seconds=100.0,
            reactivation_window_seconds=500.0,
            fresh_evidence_window_seconds=50.0,
        )
    )


def _record(
    record_id: str,
    *,
    created_at: str,
    text: str | None = None,
    provenance_refs: tuple[str, ...] = (),
    contradicts: tuple[str, ...] = (),
) -> MemoryRecord:
    return MemoryRecord.build(
        record_id=record_id,
        revision=1,
        source_id=f"source-{record_id}",
        source_kind="human",
        provenance_refs=provenance_refs,
        created_at=created_at,
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at="2027-01-01T00:00:00+00:00",
        epistemic_kind="source",
        contradicts=contradicts,
        text=text or record_id,
    )


def _service(tmp_path: Path, *, horizon: bool = True) -> GovernedMemoryService:
    return GovernedMemoryService(
        MemoryStore(tmp_path / "canonical.sqlite3"),
        _policy(),
        evidence_horizon=_horizon() if horizon else None,
    )


def _publish(
    service: GovernedMemoryService,
    record: MemoryRecord,
    operation_id: str,
) -> None:
    result = service.put(
        record,
        principal_id="operator",
        task_id="write",
        authority=_authority("memory.write"),
        operation_id=operation_id,
    )
    assert result.status == "ok"
    service.store.mark_receipt_published(operation_id)


def test_active_memory_is_context_admissible_and_receipted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    record = _record(
        "active",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, record, "put-active")

    result = service.get(
        "active",
        principal_id="operator",
        task_id="read",
        authority=_authority("memory.read"),
        evaluated_at_utc="2026-09-21T20:01:00+00:00",
    )

    assert result.status == "ok"
    assert result.record == record
    horizon = result.evidence_horizon_receipts[0]
    assert horizon.status == "ACTIVE"
    assert horizon.context_admissible is True
    assert horizon.operational_authority is False
    assert horizon.action_authority is False
    assert horizon.execution_authority is False
    read = result.read_admissibility_receipts[0]
    assert read.evidence_horizon_status == "ACTIVE"
    assert read.evidence_horizon_receipt_sha256 == horizon.receipt_sha256


def test_retrievable_memory_can_be_blocked_from_current_context(tmp_path: Path) -> None:
    service = _service(tmp_path)
    record = _record(
        "old",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, record, "put-old")

    # Canonical retention/liveness still says the record exists.
    assert (
        service.store.get(
            "old",
            now=__import__("datetime").datetime.fromisoformat(
                "2026-09-21T20:03:20+00:00"
            ),
        )
        == record
    )

    result = service.get(
        "old",
        principal_id="operator",
        task_id="read",
        authority=_authority("memory.read"),
        evaluated_at_utc="2026-09-21T20:03:20+00:00",
    )

    assert result.status == "blocked"
    assert result.error_code == "MEMORY_REACTIVATION_REQUIRED"
    horizon = result.evidence_horizon_receipts[0]
    assert horizon.status == "REACTIVATION_REQUIRED"
    assert horizon.context_admissible is False
    assert horizon.retrievable_record_unchanged is True


def test_newer_exact_linked_memory_can_reactivate_context(tmp_path: Path) -> None:
    service = _service(tmp_path)
    old = _record(
        "old",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, old, "put-old")
    evidence = _record(
        "fresh",
        created_at="2026-09-21T20:03:00+00:00",
        provenance_refs=(memory_record_ref(old),),
    )
    _publish(service, evidence, "put-fresh")

    result = service.get(
        "old",
        principal_id="operator",
        task_id="read",
        authority=_authority("memory.read"),
        reactivation_record_id="fresh",
        evaluated_at_utc="2026-09-21T20:03:20+00:00",
    )

    assert result.status == "ok"
    assert result.record == old
    horizon = result.evidence_horizon_receipts[0]
    reactivation = result.reactivation_window_receipts[0]
    assert horizon.status == "REACTIVATED"
    assert horizon.reactivation_required is True
    assert horizon.reactivation_receipt_sha256 == reactivation.receipt_sha256
    assert reactivation.status == "ACCEPTED"
    assert reactivation.context_reactivated is True
    assert reactivation.canonical_record_mutated is False
    assert reactivation.retention_mutated is False
    assert reactivation.action_authority is False
    assert result.read_admissibility_receipts[0].reactivation_window_receipt_sha256 == (
        reactivation.receipt_sha256
    )


def test_unlinked_or_contradicting_evidence_cannot_reactivate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    old = _record(
        "old",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, old, "put-old")
    unlinked = _record(
        "unlinked",
        created_at="2026-09-21T20:03:00+00:00",
    )
    _publish(service, unlinked, "put-unlinked")

    unlinked_result = service.get(
        "old",
        principal_id="operator",
        task_id="read-unlinked",
        authority=_authority("memory.read"),
        reactivation_record_id="unlinked",
        evaluated_at_utc="2026-09-21T20:03:20+00:00",
    )
    assert unlinked_result.status == "blocked"
    assert unlinked_result.error_code == "MEMORY_REACTIVATION_HELD"
    assert (
        unlinked_result.reactivation_window_receipts[0].reason
        == "reactivation_evidence_missing_exact_record_ref"
    )

    contradicting = _record(
        "contradicting",
        created_at="2026-09-21T20:03:10+00:00",
        provenance_refs=(memory_record_ref(old),),
        contradicts=(old.record_id,),
    )
    _publish(service, contradicting, "put-contradicting")
    contradiction_result = service.get(
        "old",
        principal_id="operator",
        task_id="read-contradiction",
        authority=_authority("memory.read"),
        reactivation_record_id="contradicting",
        evaluated_at_utc="2026-09-21T20:03:20+00:00",
    )
    assert contradiction_result.status == "blocked"
    assert (
        contradiction_result.reactivation_window_receipts[0].reason
        == "reactivation_evidence_contradicts_record"
    )


def test_outside_horizon_cannot_be_reactivated(tmp_path: Path) -> None:
    service = _service(tmp_path)
    old = _record(
        "old",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, old, "put-old")
    fresh = _record(
        "fresh",
        created_at="2026-09-21T20:09:00+00:00",
        provenance_refs=(memory_record_ref(old),),
    )
    _publish(service, fresh, "put-fresh")

    result = service.get(
        "old",
        principal_id="operator",
        task_id="read",
        authority=_authority("memory.read"),
        reactivation_record_id="fresh",
        evaluated_at_utc="2026-09-21T20:09:10+00:00",
    )

    assert result.status == "blocked"
    assert result.error_code == "MEMORY_OUTSIDE_EVIDENCE_HORIZON"
    assert result.evidence_horizon_receipts[0].status == "OUTSIDE_HORIZON"
    assert result.reactivation_window_receipts == ()


def test_horizon_disabled_preserves_existing_read_behavior(tmp_path: Path) -> None:
    service = _service(tmp_path, horizon=False)
    old = _record(
        "old",
        created_at="2026-09-21T20:00:00+00:00",
    )
    _publish(service, old, "put-old")

    result = service.get(
        "old",
        principal_id="operator",
        task_id="read",
        authority=_authority("memory.read"),
        evaluated_at_utc="2026-09-21T23:00:00+00:00",
    )

    assert result.status == "ok"
    assert result.evidence_horizon_receipts == ()
    assert result.read_admissibility_receipts[0].evidence_horizon_status is None


class _Provider:
    def __init__(self) -> None:
        self._identity = EmbeddingIdentity(
            provider="test",
            provider_version="1",
            model="test",
            model_digest="a" * 64,
            dimensions=2,
        )

    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(self, text: str, *, deadline: float) -> tuple[float, ...]:
        del deadline
        return (float(len(text)), 0.0)


class _Index:
    def __init__(self, identity: EmbeddingIdentity) -> None:
        self.embedding_identity = identity
        self.generation_id = identity.generation_id
        self.rows: dict[tuple[str, int], str] = {}
        self.last_eligible: tuple[tuple[str, int, str], ...] = ()

    def available(self) -> bool:
        return True

    def upsert(
        self,
        *,
        record_id: str,
        revision: int,
        record_sha256: str,
        vector: tuple[float, ...],
        identity: EmbeddingIdentity,
    ) -> None:
        del vector
        assert identity == self.embedding_identity
        self.rows[(record_id, revision)] = record_sha256

    def remove(self, record_id: str) -> None:
        for key in list(self.rows):
            if key[0] == record_id:
                del self.rows[key]

    def search(
        self,
        vector: tuple[float, ...],
        *,
        eligible_versions: tuple[tuple[str, int, str], ...],
        limit: int,
    ) -> tuple[VectorCandidate, ...]:
        del vector
        self.last_eligible = eligible_versions
        return tuple(
            VectorCandidate(
                record_id=record_id,
                revision=revision,
                record_sha256=digest,
                retrieval_distance=float(index),
            )
            for index, (record_id, revision, digest) in enumerate(
                eligible_versions[:limit]
            )
        )


def test_semantic_ranking_allowlist_excludes_stale_context(tmp_path: Path) -> None:
    provider = _Provider()
    index = _Index(provider.identity())
    service = GovernedMemoryService(
        MemoryStore(tmp_path / "canonical.sqlite3"),
        _policy(),
        retrieval_index=index,
        embedding_provider=provider,
        evidence_horizon=_horizon(),
    )
    active = _record(
        "active",
        created_at="2026-09-21T20:02:30+00:00",
        text="active memory",
    )
    stale = _record(
        "stale",
        created_at="2026-09-21T20:00:00+00:00",
        text="stale memory",
    )
    _publish(service, active, "put-active")
    _publish(service, stale, "put-stale")
    assert service.sync_index().status == "ok"

    result = service.semantic_search(
        "memory",
        principal_id="operator",
        task_id="search",
        authority=_authority("memory.read"),
        operation_id="search-1",
        evaluated_at_utc="2026-09-21T20:03:20+00:00",
    )

    assert result.status == "ok"
    assert [hit.record.record_id for hit in result.hits] == ["active"]
    assert [row[0] for row in index.last_eligible] == ["active"]
    assert result.evidence_horizon_receipts[0].status == "ACTIVE"


def test_same_horizon_inputs_are_deterministic() -> None:
    horizon = _horizon()
    record = _record(
        "one",
        created_at="2026-09-21T20:00:00+00:00",
    )

    first = horizon.evaluate(
        record,
        evaluated_at_utc="2026-09-21T20:01:00+00:00",
    )
    second = horizon.evaluate(
        record,
        evaluated_at_utc="2026-09-21T20:01:00+00:00",
    )

    assert first.horizon_receipt.to_dict() == second.horizon_receipt.to_dict()


def test_invalid_policy_windows_fail_closed() -> None:
    with pytest.raises(ValueError):
        EvidenceHorizonPolicy(
            policy_id="bad",
            active_window_seconds=100.0,
            reactivation_window_seconds=50.0,
            fresh_evidence_window_seconds=10.0,
        )
    with pytest.raises(ValueError):
        EvidenceHorizonPolicy(
            policy_id="bad",
            active_window_seconds=100.0,
            reactivation_window_seconds=500.0,
            fresh_evidence_window_seconds=101.0,
        )
