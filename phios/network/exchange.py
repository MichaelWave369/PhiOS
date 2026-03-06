"""Peer snapshot exchange primitives for federation mode."""

from __future__ import annotations

import hashlib
import json
import os
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
        self._accepted: set[str] = set()
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

    def submit_proposal(self, proposal: dict[str, Any]) -> None:
        pid = str(proposal.get("proposal_id", ""))
        if pid:
            self._pending[pid] = proposal

    def get_pending_proposals(self) -> list[dict[str, Any]]:
        return list(self._pending.values())

    def is_accepted(self, proposal_id: str) -> bool:
        return proposal_id in self._accepted

    def accept_proposal(self, proposal_id: str, operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            return {"accepted": False, "reason": "operator confirmation required"}
        proposal = self._pending.get(proposal_id)
        if not proposal:
            return {"accepted": False, "reason": "proposal not found"}
        self._accepted.add(proposal_id)
        payload = proposal.get("payload")
        warnings: list[str] = []
        if payload is None:
            return {"accepted": True, "saved_path": None, "verified": False, "snapshot_hash": None, "warnings": ["waiting for payload"]}

        recv_dir = _config_home() / "received_snapshots"
        recv_dir.mkdir(parents=True, exist_ok=True)
        saved = recv_dir / f"{proposal_id}.json"
        saved.write_text(str(payload), encoding="utf-8")

        digest = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
        expected = str(proposal.get("snapshot_hash", ""))
        verified = digest == expected
        if not verified:
            warnings.append("snapshot hash mismatch")

        self.log.log_received(str(proposal.get("from_node", "unknown")), digest, verified)
        return {
            "saved_path": str(saved),
            "verified": verified,
            "snapshot_hash": digest,
            "warnings": warnings,
        }

    def reject_proposal(self, proposal_id: str) -> None:
        self._pending.pop(proposal_id, None)
        self._accepted.discard(proposal_id)

    def receive_payload(self, proposal_id: str, payload: str) -> dict[str, Any]:
        proposal = self._pending.get(proposal_id)
        if not proposal:
            return {"received": False, "reason": "proposal not found"}
        if proposal_id not in self._accepted:
            return {"received": False, "reason": "proposal not accepted"}
        proposal["payload"] = payload
        return {"received": True}

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
        if self.server is not None:
            self.server.submit_proposal(proposal)
        return {"proposal_id": proposal_id, "status": "proposed", "peer": peer_address}

    def send_snapshot(self, peer_address: str, snapshot_path: str, proposal_id: str) -> dict[str, Any]:
        if not _localhost(peer_address) and not self._tls_configured():
            return {"status": "refused", "reason": "TLS required for non-localhost exchange"}
        if self.server is None:
            return {"status": "refused", "reason": "no exchange server"}
        if not self.server.is_accepted(proposal_id):
            return {"status": "refused", "reason": "proposal not accepted"}

        payload = Path(snapshot_path).read_text(encoding="utf-8")
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        recv = self.server.receive_payload(proposal_id, payload)
        if not recv.get("received", False):
            return {"status": "refused", "reason": str(recv.get('reason', 'receive failed'))}

        self.log.log_sent(peer_address, digest)
        archive_path = _config_home() / "exchange_archive.jsonl"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with archive_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": "snapshot_exchange_sent", "peer": peer_address, "hash": digest}) + "\n")

        return {"status": "sent", "proposal_id": proposal_id, "snapshot_hash": digest}
