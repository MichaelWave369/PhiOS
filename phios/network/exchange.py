"""Legacy local snapshot-exchange prototype.\n\nThis module does not implement an authenticated remote transport. Payloads become\naccepted only after exact proposal-id, SHA-256, and byte-size verification.\n"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _config_home() -> Path:
    root = Path(os.environ.get("PHIOS_CONFIG_HOME", str(Path.home())))
    return root / ".phi"


def _snapshot_hash(snapshot_path: str | Path) -> str:
    data = Path(snapshot_path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def _localhost(address: str) -> bool:
    return address in {"localhost", "127.0.0.1"}


_SAFE_PROPOSAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


def _valid_proposal_id(proposal_id: str) -> bool:
    return bool(_SAFE_PROPOSAL_ID.fullmatch(proposal_id))


def _proposal_metadata(proposal: dict[str, Any]) -> tuple[str, int] | None:
    expected_hash = proposal.get("snapshot_hash")
    summary = proposal.get("snapshot_summary")
    if not isinstance(expected_hash, str) or not _SHA256_HEX.fullmatch(expected_hash):
        return None
    if not isinstance(summary, dict):
        return None
    expected_size = summary.get("size")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
        return None
    return expected_hash.lower(), expected_size


def _payload_bytes(payload: str | bytes) -> bytes:
    return payload if isinstance(payload, bytes) else payload.encode("utf-8")


class ExchangeLog:
    def __init__(self) -> None:
        self.path = _config_home() / "exchange_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: dict[str, Any]) -> None:
        entry["at"] = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def log_sent(self, to_node: str, snapshot_hash: str) -> None:
        self._append({"direction": "sent", "to_node": to_node, "snapshot_hash": snapshot_hash})

    def log_received(self, from_node: str, snapshot_hash: str, verified: bool) -> None:
        self._append({"direction": "received", "from_node": from_node, "snapshot_hash": snapshot_hash, "verified": verified})

    def get_history(self, limit: int = 9) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return []
        return [json.loads(line) for line in lines[-limit:]]


class PhiExchangeServer:
    def __init__(self) -> None:
        self.running = False
        self.port: int | None = None
        self._listener: socket.socket | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._authorized: set[str] = set()
        self._verified: set[str] = set()
        self._quarantined: dict[str, str] = {}
        self._last_reason = "stopped"
        self.log = ExchangeLog()

    def start(self, port: int = 36900) -> None:
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(1)
            self._listener = listener
            self.running = True
            self.port = port
            self._last_reason = "running"
        except OSError:
            self.running = False
            self.port = None
            self._last_reason = "port conflict"

    def stop(self) -> None:
        try:
            if self._listener is not None:
                self._listener.close()
        except OSError:
            pass
        self._listener = None
        self.running = False
        self.port = None
        self._last_reason = "stopped"

    def submit_proposal(self, proposal: dict[str, Any]) -> bool:
        pid = str(proposal.get("proposal_id", ""))
        if not _valid_proposal_id(pid):
            return False
        if _proposal_metadata(proposal) is None:
            return False
        if pid in self._pending or pid in self._verified:
            return False
        self._pending[pid] = dict(proposal)
        self._pending[pid]["payload"] = proposal.get("payload")
        return True

    def get_pending_proposals(self) -> list[dict[str, Any]]:
        return list(self._pending.values())

    def is_authorized(self, proposal_id: str) -> bool:
        return proposal_id in self._authorized

    def is_accepted(self, proposal_id: str) -> bool:
        return proposal_id in self._verified

    def _quarantine_result(
        self,
        proposal_id: str,
        proposal: dict[str, Any],
        *,
        reason: str,
        digest: str,
    ) -> dict[str, Any]:
        self._authorized.discard(proposal_id)
        self._verified.discard(proposal_id)
        self._quarantined[proposal_id] = reason
        proposal["payload"] = None
        self.log.log_received(str(proposal.get("from_node", "unknown")), digest, False)
        return {
            "accepted": False,
            "authorized": False,
            "received": True,
            "saved_path": None,
            "verified": False,
            "state": "quarantined",
            "snapshot_hash": digest,
            "warnings": [reason],
            "reason": reason,
        }

    def _verify_and_persist(
        self,
        proposal_id: str,
        proposal: dict[str, Any],
        payload: str | bytes,
    ) -> dict[str, Any]:
        metadata = _proposal_metadata(proposal)
        if metadata is None:
            return {
                "accepted": False,
                "authorized": False,
                "received": False,
                "saved_path": None,
                "verified": False,
                "state": "refused",
                "snapshot_hash": None,
                "warnings": ["invalid proposal metadata"],
                "reason": "invalid proposal metadata",
            }

        expected_hash, expected_size = metadata
        data = _payload_bytes(payload)
        digest = hashlib.sha256(data).hexdigest()
        actual_size = len(data)

        if digest != expected_hash:
            return self._quarantine_result(
                proposal_id,
                proposal,
                reason="snapshot hash mismatch",
                digest=digest,
            )
        if actual_size != expected_size:
            return self._quarantine_result(
                proposal_id,
                proposal,
                reason="snapshot size mismatch",
                digest=digest,
            )

        recv_dir = _config_home() / "received_snapshots"
        recv_dir.mkdir(parents=True, exist_ok=True)
        saved = recv_dir / f"{proposal_id}.json"

        try:
            with saved.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            existing = saved.read_bytes()
            existing_hash = hashlib.sha256(existing).hexdigest()
            if existing_hash != expected_hash or len(existing) != expected_size:
                return self._quarantine_result(
                    proposal_id,
                    proposal,
                    reason="verified destination already exists with different content",
                    digest=digest,
                )

        self._authorized.discard(proposal_id)
        self._quarantined.pop(proposal_id, None)
        self._verified.add(proposal_id)
        proposal["payload"] = None
        self.log.log_received(str(proposal.get("from_node", "unknown")), digest, True)
        return {
            "accepted": True,
            "authorized": False,
            "received": True,
            "saved_path": str(saved),
            "verified": True,
            "state": "verified",
            "snapshot_hash": digest,
            "warnings": [],
        }

    def accept_proposal(self, proposal_id: str, operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            return {"accepted": False, "reason": "operator confirmation required"}
        if not _valid_proposal_id(proposal_id):
            return {"accepted": False, "reason": "invalid proposal id"}
        proposal = self._pending.get(proposal_id)
        if not proposal:
            return {"accepted": False, "reason": "proposal not found"}
        if _proposal_metadata(proposal) is None:
            return {"accepted": False, "reason": "invalid proposal metadata"}
        if proposal_id in self._quarantined:
            return {
                "accepted": False,
                "authorized": False,
                "verified": False,
                "state": "quarantined",
                "reason": self._quarantined[proposal_id],
            }
        if proposal_id in self._verified:
            saved = _config_home() / "received_snapshots" / f"{proposal_id}.json"
            return {
                "accepted": True,
                "authorized": False,
                "verified": True,
                "state": "verified",
                "saved_path": str(saved),
            }

        payload = proposal.get("payload")
        if payload is not None:
            return self._verify_and_persist(proposal_id, proposal, payload)

        self._authorized.add(proposal_id)
        return {
            "accepted": False,
            "authorized": True,
            "saved_path": None,
            "verified": False,
            "state": "awaiting_payload",
            "snapshot_hash": None,
            "warnings": ["waiting for payload"],
        }

    def reject_proposal(self, proposal_id: str) -> None:
        self._pending.pop(proposal_id, None)
        self._authorized.discard(proposal_id)
        self._verified.discard(proposal_id)
        self._quarantined.pop(proposal_id, None)

    def receive_payload(self, proposal_id: str, payload: str | bytes) -> dict[str, Any]:
        if not _valid_proposal_id(proposal_id):
            return {"received": False, "verified": False, "reason": "invalid proposal id"}
        proposal = self._pending.get(proposal_id)
        if not proposal:
            return {"received": False, "verified": False, "reason": "proposal not found"}
        if proposal_id not in self._authorized:
            return {"received": False, "verified": False, "reason": "proposal not authorized for payload"}
        return self._verify_and_persist(proposal_id, proposal, payload)

    def status(self) -> dict[str, object]:
        return {"running": self.running, "port": self.port, "last_reason": self._last_reason}


class PhiExchangeClient:
    def __init__(self, server: PhiExchangeServer | None = None) -> None:
        self.server = server
        self.log = ExchangeLog()

    def _tls_configured(self) -> bool:
        cert = os.environ.get("PHIOS_TLS_CERT")
        key = os.environ.get("PHIOS_TLS_KEY")
        return bool(cert and key and Path(cert).exists() and Path(key).exists())

    def propose_exchange(self, peer_address: str, snapshot_path: str, operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            return {"status": "refused", "reason": "operator confirmation required"}
        if not _localhost(peer_address) and not self._tls_configured():
            return {"status": "refused", "reason": "TLS required for non-localhost exchange"}

        snapshot_file = Path(snapshot_path)
        if not snapshot_file.exists():
            return {"status": "refused", "reason": "snapshot not found"}

        digest = _snapshot_hash(snapshot_file)
        proposal_id = digest[:12]
        summary = {"name": snapshot_file.name, "size": snapshot_file.stat().st_size, "hash": digest[:12]}
        proposal = {
            "proposal_id": proposal_id,
            "from_node": "local",
            "from_address": "127.0.0.1",
            "proposed_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_summary": summary,
            "snapshot_hash": digest,
            "snapshot_path": str(snapshot_file),
            "payload": None,
        }
        if self.server is not None and not self.server.submit_proposal(proposal):
            return {"status": "refused", "reason": "invalid or duplicate proposal metadata"}
        return {"proposal_id": proposal_id, "status": "proposed", "peer": peer_address}

    def send_snapshot(self, peer_address: str, snapshot_path: str, proposal_id: str) -> dict[str, Any]:
        if not _localhost(peer_address) and not self._tls_configured():
            return {"status": "refused", "reason": "TLS required for non-localhost exchange"}
        if self.server is None:
            return {"status": "refused", "reason": "no exchange server"}
        if not self.server.is_authorized(proposal_id):
            return {"status": "refused", "reason": "proposal not authorized for payload"}

        payload = Path(snapshot_path).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        recv = self.server.receive_payload(proposal_id, payload)
        if not recv.get("verified", False):
            return {
                "status": "refused",
                "proposal_id": proposal_id,
                "state": str(recv.get("state", "refused")),
                "reason": str(recv.get("reason", "receiver rejected payload")),
            }

        self.log.log_sent(peer_address, digest)
        archive_path = _config_home() / "exchange_archive.jsonl"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with archive_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": "snapshot_exchange_sent", "peer": peer_address, "hash": digest}) + "\n")

        return {"status": "sent", "proposal_id": proposal_id, "snapshot_hash": digest}
