import time
from pathlib import Path

from phios.mandala import AuthorityContext
from phios.memory import (
    EmbeddingIdentity,
    GovernedMemoryService,
    MemoryAccessPolicy,
    MemoryPolicyRule,
    MemoryRecord,
    MemoryStore,
    VectorCandidate,
)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._identity = EmbeddingIdentity(
            provider="fake",
            provider_version="1",
            model="fixture",
            model_digest="a" * 64,
            dimensions=3,
        )

    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(self, text: str, *, deadline: float) -> tuple[float, ...]:
        assert deadline > time.monotonic()
        self.calls.append(text)
        base = float(len(text) % 10) / 10.0
        return (base, base, base)


class FakeIndex:
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
        self.last_eligible = eligible_versions
        out: list[VectorCandidate] = []
        for record_id, revision, digest in eligible_versions:
            stored = self.rows.get((record_id, revision))
            if stored is None or stored[0] != digest:
                continue
            distance = sum((a - b) ** 2 for a, b in zip(vector, stored[1])) ** 0.5
            out.append(
                VectorCandidate(
                    record_id=record_id,
                    revision=revision,
                    record_sha256=digest,
                    retrieval_distance=distance,
                )
            )
        return tuple(sorted(out, key=lambda item: (item.retrieval_distance, item.record_id))[:limit])


class LeakyIndex(FakeIndex):
    def search(
        self,
        vector: tuple[float, ...],
        *,
        eligible_versions: tuple[tuple[str, int, str], ...],
        limit: int,
    ) -> tuple[VectorCandidate, ...]:
        del vector, eligible_versions, limit
        return tuple(
            VectorCandidate(
                record_id=record_id,
                revision=revision,
                record_sha256=digest,
                retrieval_distance=0.0,
            )
            for (record_id, revision), (digest, _vector) in self.rows.items()
        )


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def _record(record_id: str, *, scope: str, text: str) -> MemoryRecord:
    return MemoryRecord.build(
        record_id=record_id,
        revision=1,
        source_id=f"source-{record_id}",
        source_kind="human",
        provenance_refs=(),
        created_at="2026-09-20T20:00:00+00:00",
        scope_id=scope,
        classification="operator",
        retention_policy_id="retain",
        expires_at="2026-10-20T20:00:00+00:00",
        epistemic_kind="source",
        text=text,
    )


def _service(tmp_path: Path, *, leaky: bool = False) -> tuple[GovernedMemoryService, FakeProvider, FakeIndex]:
    policy = MemoryAccessPolicy(
        (
            MemoryPolicyRule(
                principal_id="admin",
                scopes=("private", "secret"),
                classifications=("operator",),
            ),
            MemoryPolicyRule(
                principal_id="operator",
                scopes=("private",),
                classifications=("operator",),
            ),
        )
    )
    provider = FakeProvider()
    index: FakeIndex = LeakyIndex(provider.identity()) if leaky else FakeIndex(provider.identity())
    service = GovernedMemoryService(
        MemoryStore(tmp_path / "canonical.sqlite3"),
        policy,
        retrieval_index=index,
        embedding_provider=provider,
    )
    return service, provider, index


def _put_and_publish(
    service: GovernedMemoryService,
    record: MemoryRecord,
    *,
    operation_id: str,
) -> None:
    result = service.put(
        record,
        principal_id="admin",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id=operation_id,
    )
    assert result.status == "ok"
    service.store.mark_receipt_published(operation_id)


def test_authorization_filters_before_ranking_and_receipts_embedding_identity(tmp_path: Path) -> None:
    service, _provider, index = _service(tmp_path)
    private = _record("private-1", scope="private", text="private memory")
    secret = _record("secret-1", scope="secret", text="secret memory")
    _put_and_publish(service, private, operation_id="put-private")
    _put_and_publish(service, secret, operation_id="put-secret")
    sync = service.sync_index()
    assert sync.status == "ok"
    assert sync.indexed == 2

    result = service.semantic_search(
        "memory",
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
        operation_id="search-1",
    )
    assert result.status == "ok"
    assert [hit.record.record_id for hit in result.hits] == ["private-1"]
    assert len(result.read_admissibility_receipts) == 1
    admissibility = result.read_admissibility_receipts[0]
    assert admissibility.record_id == "private-1"
    assert admissibility.operational_authority is False
    assert admissibility.action_authority is False
    assert admissibility.execution_authority is False
    assert index.last_eligible == (("private-1", 1, private.record_sha256),)
    receipt = next(
        item for item in service.store.pending_receipts() if item["operation_id"] == "search-1"
    )
    assert receipt["embedding_identity"]["model_digest"] == "a" * 64
    assert receipt["index_generation"] == index.generation_id
    assert receipt["promotion_status"] == "not_promoted"
    assert receipt["action_authority"] is False


def test_denied_search_never_calls_embedding_provider(tmp_path: Path) -> None:
    service, provider, _index = _service(tmp_path)
    _put_and_publish(
        service,
        _record("private-1", scope="private", text="stored"),
        operation_id="put",
    )
    before = len(provider.calls)
    result = service.semantic_search(
        "query",
        principal_id="unknown",
        task_id="task",
        authority=_authority("memory.read"),
        operation_id="denied-search",
    )
    assert result.status == "blocked"
    assert len(provider.calls) == before


def test_backend_candidate_is_revalidated_against_canonical_policy(tmp_path: Path) -> None:
    service, _provider, index = _service(tmp_path, leaky=True)
    private = _record("private-1", scope="private", text="private")
    secret = _record("secret-1", scope="secret", text="secret")
    _put_and_publish(service, private, operation_id="put-private")
    _put_and_publish(service, secret, operation_id="put-secret")
    assert service.sync_index().status == "ok"
    assert ("secret-1", 1) in index.rows

    result = service.semantic_search(
        "query",
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
        operation_id="search",
    )
    assert result.status == "ok"
    assert [hit.record.record_id for hit in result.hits] == ["private-1"]


def test_missing_backend_is_unavailable_without_lexical_fallback(tmp_path: Path) -> None:
    policy = MemoryAccessPolicy(
        (
            MemoryPolicyRule(
                principal_id="operator",
                scopes=("private",),
                classifications=("operator",),
            ),
        )
    )
    service = GovernedMemoryService(MemoryStore(tmp_path / "canonical.sqlite3"), policy)
    record = _record("one", scope="private", text="exact lexical match")
    result = service.put(
        record,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id="put",
    )
    assert result.status == "ok"
    service.store.mark_receipt_published("put")
    search = service.semantic_search(
        "exact lexical match",
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.read"),
        operation_id="search",
    )
    assert search.status == "unavailable"
    assert search.hits == ()
    assert search.error_code == "SEMANTIC_RETRIEVAL_UNAVAILABLE"


def test_delete_before_sync_prevents_delayed_upsert_and_purges_index(tmp_path: Path) -> None:
    service, _provider, index = _service(tmp_path)
    record = _record("one", scope="private", text="delete me")
    _put_and_publish(service, record, operation_id="put")
    deleted = service.delete(
        "one",
        principal_id="admin",
        task_id="task",
        authority=_authority("memory.delete"),
        operation_id="delete",
    )
    assert deleted.status == "ok"
    sync = service.sync_index()
    assert sync.status == "ok"
    assert sync.stale == 1
    assert sync.removed == 1
    assert index.rows == {}
