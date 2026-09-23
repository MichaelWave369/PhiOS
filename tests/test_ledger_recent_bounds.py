from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.mandala.ledger import MandalaReceiptLedger
from phios.spine.ledger import RealityLedger


@pytest.mark.parametrize("ledger_cls", [MandalaReceiptLedger, RealityLedger])
def test_recent_zero_returns_no_rows(ledger_cls, tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"receipt_id": f"r-{index}"})
            for index in range(3)
        )
        + "\n",
        encoding="utf-8",
    )

    ledger = ledger_cls(path)

    assert ledger.recent(0) == []


@pytest.mark.parametrize("ledger_cls", [MandalaReceiptLedger, RealityLedger])
def test_recent_positive_limit_remains_tail_bounded(ledger_cls, tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"receipt_id": f"r-{index}"})
            for index in range(5)
        )
        + "\n",
        encoding="utf-8",
    )

    ledger = ledger_cls(path)
    rows = ledger.recent(2)

    assert [row["receipt_id"] for row in rows] == ["r-3", "r-4"]


@pytest.mark.parametrize("ledger_cls", [MandalaReceiptLedger, RealityLedger])
def test_recent_negative_limit_is_rejected(ledger_cls, tmp_path: Path) -> None:
    ledger = ledger_cls(tmp_path / "ledger.jsonl")

    with pytest.raises(ValueError, match="non-negative"):
        ledger.recent(-1)


@pytest.mark.parametrize("bad_limit", [True, False, 1.5, "1", None])
@pytest.mark.parametrize("ledger_cls", [MandalaReceiptLedger, RealityLedger])
def test_recent_rejects_non_integer_or_boolean_limits(
    ledger_cls,
    bad_limit,
    tmp_path: Path,
) -> None:
    ledger = ledger_cls(tmp_path / "ledger.jsonl")

    with pytest.raises(TypeError, match="integer"):
        ledger.recent(bad_limit)
