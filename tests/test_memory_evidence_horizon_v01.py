from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from phios.mandala import AuthorityContext
from phios.memory import (
    EmbeddingIdentity,
    EvidenceHorizonController,
    EvidenceHorizonPolicy,
    GovernedMemoryService,
    MemoryAccessPolicy,
    MemoryPolicyRule,
    MemoryRecord,
    MemoryStore,
    VectorCandidate,
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


def _controller(
    *,
    max_age: float = 30.0,
    reactivation_window: float = 60.0,
) -> EvidenceHorizonController:
    return EvidenceHorizonController(
        EvidenceHorizonPolicy(
            policy_id="memory-context-horizon",
            version="0.1",
            max_context_age_seconds=max_age,
            reactivation_window_seconds=reactivation_window,
        )
    )


def _record(
    *,
    record_id: str = "memory-1",
    revision: int = 1,
    created_at: datetime,
    text: str = "context",
    provenance_refs: tuple[str, ...] = ("source:initial",),
) -> MemoryRecord:
    return MemoryRecord.build(
        record_id=record_id,
        revision=revision,
        source_id="operator",
        source_kind="human",
        provenance_refs=provenance_refs,
        created_at=created_at.astimezone(UTC).isoformat(),
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at=(created_at + timedelta(days=7)).astimezone(UTC).isoformat(),
        epistemic_kind="source",
        text=text,
    )


def _service(
    tmp_path: Path,
    *,
    max_age: float = 30.0,
    reactivation_window: float = 60.0,
    retrieval_index=None,
    embedding_provider=None,
) -> GovernedMemoryService:
    return GovernedMemoryService(
        MemoryStore(tmp_path / "canonical.sqlite3"),
        _policy(),
        retrieval_index=retrieval_index,
        embedding_provider=embedding_provider,
        evidence_horizon=_controller(
            max_age=max_age,
            reactivation_window=reactivation_window,
        ),
    )


def _put_and_publish(
    service: GovernedMemoryService,
    record: MemoryRecord,
    *,
    operation_id: str,
    reconsolidation_evidence_refs: tuple[str, ...] = (),
) -> None:
    result = service.put(
        record,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id=operation_id,
        reconsolidation_evidence_refs=reconsolidation_evidence_refs,
    )
    assert result.status == "ok"
    service.store.mark_receipt_published(operation_id)


def test_horizon_distinguishes_admissible_reactivation_and_outside() -> None:
    controller = _controller(max_age=10.0, reactivation_window=20.0)
    record = _record(
        created_at=datetime(2026, 9, 21, 20, 0, 0, tzinfo=UTC),
    )

    at_boundary = controller.evaluate(
        record,
        evaluated_at_utc="2026-09-21T20:00:10+00:00",
    )
    assert at_boundary.horizon.status == "ADMISSIBLE"
    assert at_boundary.horizon.readable_as_context is True
    assert at_boundary.reactivation is None

    needs_reactivation = controller.evaluate(
        record,
        evaluated_at_utc="2026-09-21T20:00:11+00:00",
    )
    assert needs_reactivation.horizon.status == "REACTIVATION_REQUIRED"
    assert needs_reactivation.horizon.readable_as_context is False
    assert needs_reactivation.reactivation is not None
    assert needs_reactivation.reactivation.within_window is True
    assert needs_reactivation.reactivation.reactivation_authorized is False
    assert needs_reactivation.reactivation.action_authority is False

    outside = controller.evaluate(
        record,
        evaluated_at_utc="2026-09-21T20:00:31+00:00",
    )
    assert outside.horizon.status == "OUTSIDE_HORIZON"
    assert outside.horizon.readable_as_context is False
    assert outside.reactivation is not None
    assert outside.reactivation.within_window is False


def test_stale_record_remains_canonical_but_is_not_returned_as_context(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    service = _service(
        tmp_path,
        max_age=1.0,
        reactivation_window=3600.0,
    )
    record = _record(created_at=now - timedelta(seconds=10))
    _put_and_publish(service, record, operation_id="put-stale")

    assert service.store.get(record.record_id) is not None

    result = service.get(
        record.record_id,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
    )

    assert result.status == "degraded"
    assert result.record is None
    assert result.error_code == "MEMORY_REACTIVATION_REQUIRED"
    assert len(result.evidence_horizon_receipts) == 1
    assert result.evidence_horizon_receipts[0].readable_as_context is False
    assert len(result.reactivation_window_receipts) == 1
    assert result.reactivation_window_receipts[0].reactivation_completed is False


def test_fresh_record_still_returns_read_admissibility_receipt(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    service = _service(tmp_path, max_age=3600.0)
    record = _record(created_at=now - timedelta(seconds=1))
    _put_and_publish(service, record, operation_id="put-fresh")

    result = service.get(
        record.record_id,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
    )

    assert result.status == "ok"
    assert result.record == record
    assert len(result.evidence_horizon_receipts) == 1
    assert result.evidence_horizon_receipts[0].status == "ADMISSIBLE"
    assert len(result.read_admissibility_receipts) == 1
    assert result.read_admissibility_receipts[0].action_authority is False


def test_stale_revision_requires_fresh_reconsolidation_provenance(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    service = _service(
        tmp_path,
        max_age=5.0,
        reactivation_window=120.0,
    )
    previous = _record(
        created_at=now - timedelta(seconds=30),
        provenance_refs=("source:initial",),
    )
    _put_and_publish(service, previous, operation_id="put-v1")

    candidate = _record(
        revision=2,
        created_at=now,
        text="revalidated context",
        provenance_refs=("source:initial", "evidence:fresh-observation"),
    )

    blocked = service.put(
        candidate,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id="put-v2-blocked",
    )
    assert blocked.status == "invalid"
    assert blocked.error_code is not None
    assert blocked.error_code.startswith("MEMORY_RECONSOLIDATION_BLOCKED:")

    accepted = service.put(
        candidate,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id="put-v2",
        reconsolidation_evidence_refs=("evidence:fresh-observation",),
    )
    assert accepted.status == "ok"


class _Provider:
    def __init__(self) -> None:
        self._identity = EmbeddingIdentity(
            provider="fake",
            provider_version="1",
            model="fixture",
            model_digest="a" * 64,
            dimensions=2,
        )

    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(self, text: str, *, deadline: float) -> tuple[float, ...]:
        assert deadline > time.monotonic()
        value = float(len(text) % 10) / 10.0
        return (value, value)


class _Index:
    def __init__(self, identity: EmbeddingIdentity) -> None:
        self.embedding_identity = identity
        self.generation_id = identity.generation_id
        self.rows: dict[tuple[str, int], tuple[str, tuple[float, ...]]] = {}
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
        assert identity == self.embedding_identity
        self.rows[(record_id, revision)] = (record_sha256, vector)

    def remove(self, record_id: str) -> None:
        for key in [key for key in self.rows if key[0] == record_id]:
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


def test_semantic_search_filters_horizon_before_vector_ranking(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    provider = _Provider()
    index = _Index(provider.identity())
    service = _service(
        tmp_path,
        max_age=5.0,
        reactivation_window=300.0,
        retrieval_index=index,
        embedding_provider=provider,
    )
    stale = _record(
        record_id="stale",
        created_at=now - timedelta(seconds=30),
        text="old context",
    )
    fresh = _record(
        record_id="fresh",
        created_at=now - timedelta(seconds=1),
        text="fresh context",
    )
    _put_and_publish(service, stale, operation_id="put-stale")
    _put_and_publish(service, fresh, operation_id="put-fresh")
    assert service.sync_index().status == "ok"

    result = service.semantic_search(
        "context",
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
        operation_id="search-horizon",
    )

    assert result.status == "ok"
    assert [hit.record.record_id for hit in result.hits] == ["fresh"]
    assert [item[0] for item in index.last_eligible] == ["fresh"]
    statuses = {
        receipt.record_id: receipt.status
        for receipt in result.evidence_horizon_receipts
    }
    assert statuses == {
        "fresh": "ADMISSIBLE",
        "stale": "REACTIVATION_REQUIRED",
    }
