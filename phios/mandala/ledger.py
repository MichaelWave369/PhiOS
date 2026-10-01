from __future__ import annotations

from pathlib import Path

from phios.state_io import append_jsonl, read_jsonl

from .receipts import ReceiptEnvelope


class MandalaReceiptLedger:
    """Append-oriented local receipt store for Mandala boundary records."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def append(self, receipt: ReceiptEnvelope) -> None:
        append_jsonl(self.path, receipt.to_dict())

    def append_if_absent(self, receipt: ReceiptEnvelope) -> bool:
        """Publish exactly once across processes, refusing identity collisions."""
        return append_jsonl(self.path, receipt.to_dict(), identity_field="receipt_id")

    def recent(self, limit: int = 10) -> list[dict[str, object]]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("recent limit must be an integer")
        if limit < 0:
            raise ValueError("recent limit must be non-negative")
        if limit == 0:
            return []
        return read_jsonl(self.path)[-limit:]

    def has_receipt(self, receipt_id: str) -> bool:
        """Return whether an exact receipt ID already exists in the append-only ledger."""

        return self.get_receipt(receipt_id) is not None

    def get_receipt(self, receipt_id: str) -> dict[str, object] | None:
        """Return the persisted receipt row for an exact receipt ID."""

        for payload in read_jsonl(self.path):
            if payload.get("receipt_id") == receipt_id:
                return payload
        return None
