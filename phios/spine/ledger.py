from __future__ import annotations

import json
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
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-max(limit, 0):]]
