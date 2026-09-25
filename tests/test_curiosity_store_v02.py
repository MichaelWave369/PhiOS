from __future__ import annotations

import json

import pytest

from phios.curiosity import CuriosityArtifact
from phios.curiosity_store import (
    CuriosityReturnPointer,
    CuriosityStore,
    CuriosityStoreError,
)


def artifact(
    *,
    kind: str,
    title: str,
    content: str,
    at: str,
    tags: tuple[str, ...] = (),
    parents: tuple[str, ...] = (),
) -> CuriosityArtifact:
    return CuriosityArtifact.build(
        artifact_kind=kind,
        title=title,
        content=content,
        created_at=at,
        created_by="operator:mikey",
        tags=tags,
        parent_artifact_sha256s=parents,
    )


def build_store(tmp_path) -> tuple[
    CuriosityStore,
    CuriosityArtifact,
    CuriosityArtifact,
    CuriosityArtifact,
]:
    store = CuriosityStore(tmp_path / "curiosity")
    root = artifact(
        kind="symbol",
        title="Nested bubble gear",
        content="A nested gear and bubble symbol for recursive structure.",
        at="2026-09-25T15:00:00+00:00",
        tags=("gear", "bubble", "recursion"),
    )
    child = artifact(
        kind="question",
        title="Could the gears have rhythm?",
        content="Explore whether the gear metaphor maps usefully to rhythm.",
        at="2026-09-25T15:10:00+00:00",
        tags=("gear", "music", "rhythm"),
        parents=(root.curiosity_artifact_sha256,),
    )
    unrelated = artifact(
        kind="creative_seed",
        title="Open-source neighborhood BBS",
        content="A community network seed built around local communication.",
        at="2026-09-25T15:20:00+00:00",
        tags=("bbs", "community", "network"),
    )
    assert store.append_artifact(root)
    assert store.append_artifact(child)
    assert store.append_artifact(unrelated)
    return store, root, child, unrelated


def test_append_artifact_is_append_only_and_retry_safe(tmp_path) -> None:
    store = CuriosityStore(tmp_path / "curiosity")
    item = artifact(
        kind="dream_fragment",
        title="Server cathedral",
        content="Endless racks connected like a glowing nervous system.",
        at="2026-09-25T15:00:00+00:00",
    )

    assert store.append_artifact(item) is True
    first_bytes = store.artifacts_path.read_bytes()

    assert store.append_artifact(item) is False
    assert store.artifacts_path.read_bytes() == first_bytes
    assert store.artifacts() == [item]


def test_persisted_artifact_tampering_is_rejected(tmp_path) -> None:
    store = CuriosityStore(tmp_path / "curiosity")
    item = artifact(
        kind="symbol",
        title="Three circles",
        content="A symbolic triad.",
        at="2026-09-25T15:00:00+00:00",
    )
    store.append_artifact(item)

    payload = item.to_dict()
    payload["content"] = "Altered after sealing."
    store.artifacts_path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        CuriosityStoreError,
        match="canonical artifact",
    ):
        store.artifacts()


def test_search_filters_text_kind_and_tags(tmp_path) -> None:
    store, root, child, _ = build_store(tmp_path)

    assert store.search(query="nested gear") == [root]
    assert store.search(kinds=("question",)) == [child]
    assert store.search(tags=("GEAR", "MUSIC")) == [child]
    assert store.search(query="does-not-exist") == []


def test_search_is_newest_first(tmp_path) -> None:
    store, root, child, unrelated = build_store(tmp_path)

    assert store.search() == [unrelated, child, root]


def test_children_and_lineage_preserve_known_ancestry(tmp_path) -> None:
    store, root, child, _ = build_store(tmp_path)
    grandchild = artifact(
        kind="hypothesis",
        title="Rhythmic recursion hypothesis",
        content="A testable descendant of the symbolic rhythm question.",
        at="2026-09-25T15:30:00+00:00",
        tags=("gear", "rhythm"),
        parents=(child.curiosity_artifact_sha256,),
    )
    store.append_artifact(grandchild)

    assert store.children_of(root.curiosity_artifact_sha256) == [child]
    assert store.lineage(grandchild.curiosity_artifact_sha256) == [
        root,
        child,
        grandchild,
    ]


def test_lineage_does_not_invent_missing_ancestors(tmp_path) -> None:
    store = CuriosityStore(tmp_path / "curiosity")
    missing = "f" * 64
    item = artifact(
        kind="association",
        title="Imported association",
        content="An artifact whose earlier parent was not imported.",
        at="2026-09-25T15:00:00+00:00",
        parents=(missing,),
    )
    store.append_artifact(item)

    assert store.lineage(item.curiosity_artifact_sha256) == [item]


def test_related_prefers_direct_lineage_and_shared_tags(tmp_path) -> None:
    store, root, child, unrelated = build_store(tmp_path)

    related = store.related(root.curiosity_artifact_sha256)

    assert related
    assert related[0].artifact == child
    assert "direct_child" in related[0].reasons
    assert all(item.artifact != unrelated for item in related)


def test_related_results_carry_zero_authority(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)

    result = store.related(root.curiosity_artifact_sha256)[0]

    assert result.effect_performed is False
    assert result.operational_authority is False
    assert result.action_authority is False
    assert result.execution_authority is False


def test_return_pointer_is_deterministic_and_zero_authority(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)
    pointer = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Return to the relationship between gear timing and music.",
        context="Do not decide what the symbol means yet.",
        tags=("RHYTHM", "gear"),
    )

    assert pointer.tags == ("gear", "rhythm")
    assert len(pointer.return_pointer_sha256) == 64
    assert pointer.effect_performed is False
    assert pointer.operational_authority is False
    assert pointer.action_authority is False
    assert pointer.execution_authority is False

    assert store.append_return_pointer(pointer) is True
    assert store.append_return_pointer(pointer) is False
    assert store.return_pointers() == [pointer]


def test_return_pointer_round_trips_exactly(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)
    pointer = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Come back here.",
    )

    rebuilt = CuriosityReturnPointer.from_dict(pointer.to_dict())

    assert rebuilt == pointer


def test_return_pointer_requires_local_target(tmp_path) -> None:
    store = CuriosityStore(tmp_path / "curiosity")
    pointer = CuriosityReturnPointer.build(
        artifact_sha256="d" * 64,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="This target is absent.",
    )

    with pytest.raises(
        CuriosityStoreError,
        match="not present",
    ):
        store.append_return_pointer(pointer)


def test_latest_return_pointer_returns_newest_without_rewriting_old(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)
    first = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="First return path.",
    )
    second = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T17:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="A later return path that preserves the first.",
    )
    store.append_return_pointer(first)
    first_bytes = store.return_pointers_path.read_bytes()
    store.append_return_pointer(second)

    assert store.return_pointers_path.read_bytes().startswith(first_bytes)
    assert store.latest_return_pointer(
        root.curiosity_artifact_sha256
    ) == second


def test_return_pointer_tampering_is_rejected(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)
    pointer = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Preserve this exact return path.",
    )
    store.append_return_pointer(pointer)

    payload = pointer.to_dict()
    payload["return_prompt"] = "Tampered."
    store.return_pointers_path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        CuriosityStoreError,
        match="canonical pointer",
    ):
        store.return_pointers()


def test_return_pointer_rejects_authority_tampering() -> None:
    pointer = CuriosityReturnPointer.build(
        artifact_sha256="a" * 64,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Return later.",
    )
    payload = pointer.to_dict()
    payload["action_authority"] = True

    with pytest.raises(CuriosityStoreError, match="cannot carry"):
        CuriosityReturnPointer.from_dict(payload)


def test_recent_return_pointers_are_newest_first(tmp_path) -> None:
    store, root, child, _ = build_store(tmp_path)
    older = CuriosityReturnPointer.build(
        artifact_sha256=root.curiosity_artifact_sha256,
        created_at="2026-09-25T16:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Older.",
    )
    newer = CuriosityReturnPointer.build(
        artifact_sha256=child.curiosity_artifact_sha256,
        created_at="2026-09-25T17:00:00+00:00",
        created_by="operator:mikey",
        return_prompt="Newer.",
    )
    store.append_return_pointer(older)
    store.append_return_pointer(newer)

    assert store.recent_return_pointers(limit=1) == [newer]


def test_limit_validation(tmp_path) -> None:
    store, root, _, _ = build_store(tmp_path)

    with pytest.raises(TypeError):
        store.search(limit=True)
    with pytest.raises(ValueError):
        store.related(root.curiosity_artifact_sha256, limit=-1)
    with pytest.raises(ValueError):
        store.recent_return_pointers(limit=-1)
