import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")

from phios.memory import EmbeddingIdentity, SqliteVecIndex


def _identity() -> EmbeddingIdentity:
    return EmbeddingIdentity(
        provider="test",
        provider_version="1",
        model="fixture",
        model_digest="a" * 64,
        dimensions=3,
    )


def test_real_sqlite_vec_ranks_only_pre_authorized_versions(tmp_path: Path) -> None:
    identity = _identity()
    index = SqliteVecIndex(tmp_path / "vectors.sqlite3", identity=identity)
    index.upsert(
        record_id="allowed",
        revision=1,
        record_sha256="1" * 64,
        vector=(0.0, 0.0, 0.0),
        identity=identity,
    )
    index.upsert(
        record_id="secret",
        revision=1,
        record_sha256="2" * 64,
        vector=(0.01, 0.01, 0.01),
        identity=identity,
    )
    hits = index.search(
        (0.01, 0.01, 0.01),
        eligible_versions=(("allowed", 1, "1" * 64),),
        limit=10,
    )
    assert [hit.record_id for hit in hits] == ["allowed"]
    assert hits[0].retrieval_distance > 0


def test_remove_purges_all_vectors_for_record(tmp_path: Path) -> None:
    identity = _identity()
    index = SqliteVecIndex(tmp_path / "vectors.sqlite3", identity=identity)
    index.upsert(
        record_id="one",
        revision=1,
        record_sha256="1" * 64,
        vector=(0.0, 0.0, 0.0),
        identity=identity,
    )
    assert index.vector_count() == 1
    index.remove("one")
    assert index.vector_count() == 0


def test_generation_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    identity = _identity()
    index = SqliteVecIndex(tmp_path / "vectors.sqlite3", identity=identity)
    other = EmbeddingIdentity(
        provider="test",
        provider_version="1",
        model="other",
        model_digest="b" * 64,
        dimensions=3,
    )
    with pytest.raises(RuntimeError, match="identity"):
        index.upsert(
            record_id="one",
            revision=1,
            record_sha256="1" * 64,
            vector=(0.0, 0.0, 0.0),
            identity=other,
        )


def test_extension_loader_and_attach_are_denied_after_initialization(tmp_path: Path) -> None:
    index = SqliteVecIndex(tmp_path / "vectors.sqlite3", identity=_identity())
    conn = index._connect()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("ATTACH DATABASE ':memory:' AS other")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT load_extension('anything')")
    finally:
        conn.close()
