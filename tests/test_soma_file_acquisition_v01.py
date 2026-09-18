import os
from pathlib import Path

import pytest

from phios.mandala import MandalaStatus
from phios.soma import AcuityStatus
from phios.spine.runtime import PhiOSSpine


def test_bounded_file_is_preserved_and_receipted(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    source = source_root / "note.md"
    source.write_bytes(b"line one\r\nline two\r")

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-ok")
    result = spine.perceive_file(
        source_root=source_root,
        relative_path="note.md",
        transforms=("normalize_newlines",),
    )

    assert result.evidence is not None
    assert Path(result.evidence.path).read_bytes() == b"line one\r\nline two\r"
    assert result.observation_text == "line one\nline two\n"
    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.acuity_status == AcuityStatus.RECOVERED.value
    assert result.receipt.acquisition_method == "bounded_file"
    assert result.receipt.source_locator == "note.md"

    receipts = spine.mandala_ledger.recent(2)
    assert [item["receipt_type"] for item in receipts] == [
        "GateReceipt",
        "PerceptionReceipt",
    ]
    assert receipts[0]["status"] == "ACCEPTED"


def test_parent_traversal_is_blocked_and_receipted(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-traversal")
    result = spine.perceive_file(
        source_root=root,
        relative_path="../secret.txt",
    )

    assert result.evidence is None
    assert result.observation_text is None
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "parent_traversal_disallowed" in result.receipt.limitations
    assert spine.mandala_ledger.recent(2)[0]["status"] == "BLOCKED"


def test_absolute_path_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-absolute")
    result = spine.perceive_file(
        source_root=root,
        relative_path=str(outside.resolve()),
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "absolute_path_disallowed" in result.receipt.limitations


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_symlinked_source_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(outside)

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-symlink")
    result = spine.perceive_file(
        source_root=root,
        relative_path="link.txt",
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "symlink_disallowed" in result.receipt.limitations


def test_file_size_limit_blocks_before_evidence_copy(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "big.txt").write_bytes(b"x" * 33)

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-size")
    result = spine.perceive_file(
        source_root=root,
        relative_path="big.txt",
        max_bytes=32,
    )

    assert result.evidence is None
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "source_too_large" in result.receipt.limitations


def test_invalid_utf8_is_quarantined_but_native_bytes_survive(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    raw = b"\xff\xfe\xfa"
    (root / "bad.txt").write_bytes(raw)

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-utf8")
    result = spine.perceive_file(
        source_root=root,
        relative_path="bad.txt",
    )

    assert result.evidence is not None
    assert Path(result.evidence.path).read_bytes() == raw
    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.receipt.acuity_status == AcuityStatus.UNAVAILABLE.value
    assert result.observation_text is None
    assert "invalid_utf8" in result.receipt.limitations


def test_unsupported_file_suffix_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "image.png").write_bytes(b"not really a png")

    spine = PhiOSSpine(state_root=tmp_path / "state", task_id="file-suffix")
    result = spine.perceive_file(
        source_root=root,
        relative_path="image.png",
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "unsupported_media_type" in result.receipt.limitations


def test_file_perception_does_not_expand_authority(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "note.txt").write_text("read only", encoding="utf-8")

    spine = PhiOSSpine(
        state_root=tmp_path / "state",
        allowed_permissions=["artifact.write"],
        task_id="file-authority",
    )
    before = spine.core.authority

    result = spine.perceive_file(
        source_root=root,
        relative_path="note.txt",
    )

    assert spine.core.authority == before
    assert result.packet.authority == before
    assert result.packet.authority.grants == ("artifact.write",)
