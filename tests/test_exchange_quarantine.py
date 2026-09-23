from __future__ import annotations

import hashlib
from pathlib import Path

from phios.network.exchange import PhiExchangeClient, PhiExchangeServer


def _proposal(payload: bytes, proposal_id: str = "abc123") -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "from_node": "test-peer",
        "snapshot_hash": hashlib.sha256(payload).hexdigest(),
        "snapshot_summary": {
            "name": "snapshot.json",
            "size": len(payload),
            "hash": hashlib.sha256(payload).hexdigest()[:12],
        },
        "payload": None,
    }


def test_exchange_rejects_unsafe_proposal_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    server = PhiExchangeServer()
    proposal = _proposal(b'{"ok":true}', proposal_id="../escaped")

    assert server.submit_proposal(proposal) is False
    assert server.get_pending_proposals() == []
    assert not (tmp_path / ".phi" / "escaped.json").exists()


def test_accept_only_authorizes_transfer_until_payload_verifies(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    payload = b'{"ok":true}'
    server = PhiExchangeServer()

    assert server.submit_proposal(_proposal(payload)) is True
    gate = server.accept_proposal("abc123", operator_confirmed=True)

    assert gate["accepted"] is False
    assert gate["authorized"] is True
    assert gate["verified"] is False
    assert gate["state"] == "awaiting_payload"
    assert server.is_authorized("abc123") is True
    assert server.is_accepted("abc123") is False
    assert not (tmp_path / ".phi" / "received_snapshots" / "abc123.json").exists()


def test_verified_payload_is_persisted_only_after_exact_hash_and_size(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    payload = b'{"ok":true}\r\n'
    server = PhiExchangeServer()

    assert server.submit_proposal(_proposal(payload)) is True
    server.accept_proposal("abc123", operator_confirmed=True)
    result = server.receive_payload("abc123", payload)

    saved = tmp_path / ".phi" / "received_snapshots" / "abc123.json"
    assert result["accepted"] is True
    assert result["verified"] is True
    assert result["state"] == "verified"
    assert result["saved_path"] == str(saved)
    assert saved.read_bytes() == payload
    assert server.is_authorized("abc123") is False
    assert server.is_accepted("abc123") is True


def test_hash_mismatch_is_quarantined_without_persistence(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    expected = b'{"a":1}'
    tampered = b'{"b":1}'
    server = PhiExchangeServer()

    assert server.submit_proposal(_proposal(expected)) is True
    server.accept_proposal("abc123", operator_confirmed=True)
    result = server.receive_payload("abc123", tampered)

    saved = tmp_path / ".phi" / "received_snapshots" / "abc123.json"
    assert result["accepted"] is False
    assert result["verified"] is False
    assert result["state"] == "quarantined"
    assert result["saved_path"] is None
    assert result["reason"] == "snapshot hash mismatch"
    assert not saved.exists()
    assert server.is_authorized("abc123") is False
    assert server.is_accepted("abc123") is False

    retry = server.accept_proposal("abc123", operator_confirmed=True)
    assert retry["state"] == "quarantined"
    assert retry["accepted"] is False


def test_size_mismatch_is_quarantined_without_persistence(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    payload = b'{"ok":true}'
    proposal = _proposal(payload)
    summary = proposal["snapshot_summary"]
    assert isinstance(summary, dict)
    summary["size"] = len(payload) + 1
    server = PhiExchangeServer()

    assert server.submit_proposal(proposal) is True
    server.accept_proposal("abc123", operator_confirmed=True)
    result = server.receive_payload("abc123", payload)

    assert result["verified"] is False
    assert result["state"] == "quarantined"
    assert result["reason"] == "snapshot size mismatch"
    assert not (tmp_path / ".phi" / "received_snapshots" / "abc123.json").exists()


def test_existing_different_destination_is_never_overwritten(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    payload = b'{"ok":true}'
    server = PhiExchangeServer()
    destination = tmp_path / ".phi" / "received_snapshots" / "abc123.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"existing-unrelated-data")

    assert server.submit_proposal(_proposal(payload)) is True
    server.accept_proposal("abc123", operator_confirmed=True)
    result = server.receive_payload("abc123", payload)

    assert result["verified"] is False
    assert result["state"] == "quarantined"
    assert "different content" in result["reason"]
    assert destination.read_bytes() == b"existing-unrelated-data"


def test_verified_proposal_cannot_consume_payload_twice(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    payload = b'{"ok":true}'
    server = PhiExchangeServer()

    assert server.submit_proposal(_proposal(payload)) is True
    server.accept_proposal("abc123", operator_confirmed=True)
    first = server.receive_payload("abc123", payload)
    second = server.receive_payload("abc123", payload)

    assert first["verified"] is True
    assert second["received"] is False
    assert second["reason"] == "proposal not authorized for payload"


def test_client_refuses_snapshot_changed_after_proposal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(b'{"a":1}')

    server = PhiExchangeServer()
    client = PhiExchangeClient(server=server)
    proposed = client.propose_exchange(
        "localhost", str(snapshot), operator_confirmed=True
    )
    proposal_id = str(proposed["proposal_id"])
    gate = server.accept_proposal(proposal_id, operator_confirmed=True)
    assert gate["state"] == "awaiting_payload"

    snapshot.write_bytes(b'{"b":1}')
    result = client.send_snapshot("localhost", str(snapshot), proposal_id)

    assert result["status"] == "refused"
    assert result["state"] == "quarantined"
    assert result["reason"] == "snapshot hash mismatch"
    assert server.is_accepted(proposal_id) is False
