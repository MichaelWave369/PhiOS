import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location(
    "phi_vault_r02", Path(__file__).resolve().parents[1] / "scripts" / "phi_vault_r02.py")
vault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vault)


@pytest.fixture
def snapshot(tmp_path):
    source = tmp_path / "conversations.json"
    raw = json.dumps([{"id": "c1", "title": "Synthetic Lab", "current_node": "b",
                       "mapping": {
                           "root": {"parent": None, "message": None},
                           "a": {"parent": "root", "message": {
                               "id": "m1", "author": {"role": "user"}, "create_time": 123,
                               "content": {"parts": ["Local Straße", {"asset": "synthetic"}]}}},
                           "b": {"parent": "a", "message": {
                               "id": "m2", "author": {"role": "assistant"},
                               "content": {"parts": ["Branch one"]}}},
                           "alternate": {"parent": "a", "message": {
                               "id": "m3", "author": {"role": "assistant"},
                               "content": {"parts": ["Branch two"]}}}
                       }}], ensure_ascii=False, indent=2).encode()
    source.write_bytes(raw)
    return source, tmp_path / "private.sqlite", raw


def test_roundtrip(snapshot, tmp_path):
    source, db, raw = snapshot
    receipt = vault.import_snapshot(source, db)
    assert receipt["nodes"] == 4
    assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
    assert vault.verify(db)["status"] == "INTEGRITY_VERIFIED"
    restored = tmp_path / "restored.json"
    vault.restore(db, restored)
    assert restored.read_bytes() == raw == source.read_bytes()


def test_search_branches_and_unicode(snapshot):
    source, db, _ = snapshot
    vault.import_snapshot(source, db)
    assert {r["node_id"] for r in vault.search(db, "BRANCH")} == {"b", "alternate"}
    assert vault.search(db, "STRASSE")[0]["message_id"] == "m1"
    assert vault.search(db, "synthetic lab", 1)[0]["conversation_id"] == "c1"
    assert vault.search(db, "' OR 1=1 --") == []
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT parent,created FROM nodes WHERE nid='a'").fetchone() == ("root", "123")


def test_refuse_overwrite(snapshot, tmp_path):
    source, db, raw = snapshot
    vault.import_snapshot(source, db)
    original = db.read_bytes()
    with pytest.raises(FileExistsError):
        vault.import_snapshot(source, db)
    with pytest.raises(FileExistsError):
        vault.restore(db, source)
    assert source.read_bytes() == raw and db.read_bytes() == original


@pytest.mark.parametrize("bad", [b'{}', b'[{"id":"a","id":"b"}]',
                                  b'[{"id":"a","mapping":{}},{"id":"a","mapping":{}}]',
                                  b'[{"id":"a","mapping":{"x":null}}]'])
def test_invalid_source(snapshot, bad):
    source, db, _ = snapshot
    source.write_bytes(bad)
    with pytest.raises(ValueError):
        vault.import_snapshot(source, db)
    assert not db.exists()


def test_git_destination(snapshot, tmp_path):
    source, _, _ = snapshot
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(vault.VaultError):
        vault.import_snapshot(source, checkout / "private.sqlite")


@pytest.mark.parametrize("statement", ["UPDATE nodes SET body='changed' WHERE nid='a'",
                                       "UPDATE snapshot SET sha256='changed'"])
def test_tamper(snapshot, tmp_path, statement):
    source, db, _ = snapshot
    vault.import_snapshot(source, db)
    with sqlite3.connect(db) as conn:
        conn.execute(statement)
    with pytest.raises(vault.VaultError):
        vault.verify(db)
    out = tmp_path / "restore.json"
    with pytest.raises(vault.VaultError):
        vault.restore(db, out)
    assert not out.exists()


def test_source_limit(snapshot, monkeypatch):
    source, db, _ = snapshot
    monkeypatch.setattr(vault, "MAX_BYTES", 5)
    with pytest.raises(vault.VaultError):
        vault.import_snapshot(source, db)
    assert not db.exists()


def test_search_missing_does_not_create(snapshot):
    _, db, _ = snapshot
    with pytest.raises(sqlite3.Error):
        vault.search(db, "test")
    assert not db.exists()
