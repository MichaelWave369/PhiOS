from __future__ import annotations

import json
import os
from pathlib import Path

from .models import ExecutionReceipt


class RealityLedger:
    """Append-only JSONL receipt ledger for the first PhiOS spine."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def append(self, receipt: ExecutionReceipt) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent(self, limit: int = 10) -> list[dict[str, object]]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("recent limit must be an integer")
        if limit < 0:
            raise ValueError("recent limit must be non-negative")
        if limit == 0 or not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def claim_binding(self, binding_sha256: str) -> bool:
        """Atomically reserve one governed binding for an execution attempt."""

        self._validate_binding_sha256(binding_sha256)
        claim_dir = self.path.parent / "binding-claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{binding_sha256}.claim"
        try:
            fd = os.open(
                claim_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(binding_sha256 + "\n")
        return True

    def release_binding_claim(self, binding_sha256: str) -> None:
        """Release a claim only when the executor was never entered."""

        self._validate_binding_sha256(binding_sha256)
        claim_path = (
            self.path.parent
            / "binding-claims"
            / f"{binding_sha256}.claim"
        )
        claim_path.unlink(missing_ok=True)

    def has_consumed_binding(self, binding_sha256: str) -> bool:
        """Return true once a bound action reached an allowed executor attempt."""

        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            provenance = entry.get("governed_provenance")
            if not isinstance(provenance, dict):
                continue
            if provenance.get("action_binding_sha256") != binding_sha256:
                continue
            if entry.get("permission_status") != "allowed":
                continue
            if entry.get("execution_status") in {"succeeded", "failed"}:
                return True
        return False

    @staticmethod
    def _validate_binding_sha256(binding_sha256: str) -> None:
        normalized = binding_sha256.strip().lower()
        if len(normalized) != 64:
            raise ValueError("binding_sha256 must be a SHA-256 hex digest")
        try:
            int(normalized, 16)
        except ValueError as exc:
            raise ValueError(
                "binding_sha256 must be a SHA-256 hex digest"
            ) from exc
