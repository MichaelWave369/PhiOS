import hashlib
from pathlib import Path

from phios.mandala import AuthorityContext, ExactnessClass, TransformationLineageBuilder
from phios.memory import (
    GovernedMemoryService,
    MemoryAccessPolicy,
    MemoryPolicyRule,
    MemoryRecord,
    MemoryStore,
)


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def _service(tmp_path: Path) -> GovernedMemoryService:
    policy = MemoryAccessPolicy(
        (
            MemoryPolicyRule(
                principal_id="operator",
                scopes=("private",),
                classifications=("operator",),
            ),
        )
    )
    return GovernedMemoryService(
        MemoryStore(tmp_path / "canonical.sqlite3"),
        policy,
    )


def _lineage(text: str):
    output_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    receipt = TransformationLineageBuilder().build(
        transform_id="test.derive",
        transform_version="v1",
        source_refs=("source:evidence",),
        source_sha256s=("a" * 64,),
        output_ref=f"memory-content:sha256:{output_sha}",
        output_sha256=output_sha,
        parameters={"mode": "test"},
        requested_exactness=ExactnessClass.INTERPRETIVE,
        added_taints=("machine_interpretation",),
        information_loss_possible=True,
        semantic_inference=True,
    )
    return receipt


def _record(
    *,
    text: str,
    lineage_sha256: str,
    exactness_class: str = ExactnessClass.INTERPRETIVE.value,
    taint_labels: tuple[str, ...] = ("machine_interpretation",),
) -> MemoryRecord:
    return MemoryRecord.build(
        record_id="derived-1",
        revision=1,
        source_id="derived-test",
        source_kind="subsystem",
        provenance_refs=("source:evidence",),
        created_at="2026-09-21T18:00:00+00:00",
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at=None,
        epistemic_kind="derived",
        derived_from=("source:evidence",),
        exactness_class=exactness_class,
        transformation_lineage_sha256s=(lineage_sha256,),
        taint_labels=taint_labels,
        text=text,
    )


def _put(
    service: GovernedMemoryService,
    record: MemoryRecord,
    *,
    lineage=(),
):
    return service.put(
        record,
        principal_id="operator",
        task_id="task",
        authority=_authority("memory.write"),
        operation_id="put-derived",
        transformation_lineage=lineage,
    )


def test_derived_memory_requires_receipted_transformation_lineage(
    tmp_path: Path,
) -> None:
    text = "derived content"
    lineage = _lineage(text)
    record = _record(text=text, lineage_sha256=lineage.receipt_sha256)

    result = _put(_service(tmp_path), record)

    assert result.status == "invalid"
    assert result.error_code == "DERIVED_MEMORY_TRANSFORMATION_LINEAGE_REQUIRED"


def test_derived_memory_output_hash_must_match_canonical_content(
    tmp_path: Path,
) -> None:
    lineage = _lineage("different output")
    record = _record(
        text="canonical derived content",
        lineage_sha256=lineage.receipt_sha256,
    )

    result = _put(_service(tmp_path), record, lineage=(lineage,))

    assert result.status == "invalid"
    assert result.error_code == "DERIVED_MEMORY_OUTPUT_HASH_MISMATCH"


def test_derived_memory_cannot_drop_transformation_taint(tmp_path: Path) -> None:
    text = "derived content"
    lineage = _lineage(text)
    record = _record(
        text=text,
        lineage_sha256=lineage.receipt_sha256,
        taint_labels=(),
    )

    result = _put(_service(tmp_path), record, lineage=(lineage,))

    assert result.status == "invalid"
    assert result.error_code == "DERIVED_MEMORY_TAINT_MISMATCH"


def test_valid_derived_memory_persists_exactness_and_lineage(
    tmp_path: Path,
) -> None:
    text = "derived content"
    lineage = _lineage(text)
    record = _record(text=text, lineage_sha256=lineage.receipt_sha256)
    service = _service(tmp_path)

    result = _put(service, record, lineage=(lineage,))
    assert result.status == "ok"
    service.store.mark_receipt_published("put-derived")

    stored = service.store.get(record.record_id)
    assert stored is not None
    assert stored.exactness_class == ExactnessClass.INTERPRETIVE.value
    assert stored.transformation_lineage_sha256s == (lineage.receipt_sha256,)
    assert stored.taint_labels == ("machine_interpretation",)


def test_derived_memory_requires_all_declared_sources_in_lineage(
    tmp_path: Path,
) -> None:
    text = "derived content"
    lineage = _lineage(text)
    record = MemoryRecord.build(
        record_id="derived-multi-source",
        revision=1,
        source_id="derived-test",
        source_kind="subsystem",
        provenance_refs=("source:evidence", "source:missing"),
        created_at="2026-09-21T18:00:00+00:00",
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at=None,
        epistemic_kind="derived",
        derived_from=("source:evidence", "source:missing"),
        exactness_class=ExactnessClass.INTERPRETIVE.value,
        transformation_lineage_sha256s=(lineage.receipt_sha256,),
        taint_labels=("machine_interpretation",),
        text=text,
    )

    result = _put(_service(tmp_path), record, lineage=(lineage,))

    assert result.status == "invalid"
    assert result.error_code == "DERIVED_MEMORY_SOURCE_LINEAGE_MISMATCH"
