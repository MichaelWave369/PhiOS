from pathlib import Path

from phios.mandala import ExactnessClass, MandalaStatus
from phios.soma import AcuityStatus
from phios.spine.runtime import PhiOSSpine


def test_native_text_is_content_addressed_and_preserved(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-perception-native")

    result = spine.perceive_text(
        source_id="operator",
        text="native source\r\nexactly",
    )

    evidence_path = Path(result.evidence.path)
    assert evidence_path.read_bytes() == b"native source\r\nexactly"
    assert result.evidence.evidence_ref == f"evidence:sha256:{result.evidence.sha256}"
    assert result.receipt.native_evidence_ref == result.evidence.evidence_ref
    assert result.receipt.native_preserved is True
    assert result.receipt.acuity_status == AcuityStatus.NATIVE.value
    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.transformation_lineage[0].exactness_class is ExactnessClass.BYTE_EXACT


def test_perception_emits_gate_then_perception_receipt(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-perception-receipts")

    result = spine.perceive_text(source_id="operator", text="observe me")
    receipts = spine.mandala_ledger.recent(2)

    assert [item["receipt_type"] for item in receipts] == [
        "GateReceipt",
        "PerceptionReceipt",
    ]
    assert receipts[0]["gate"] == "PERCEPTION"
    assert receipts[0]["status"] == "ACCEPTED"
    assert receipts[1]["status"] == "ACCEPTED"
    assert receipts[1]["native_evidence_ref"] == result.evidence.evidence_ref
    assert receipts[1]["source_id"] == "operator"


def test_normalization_marks_recovered_without_mutating_native(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-perception-recovery")
    native_text = "\ufeffline one\r\nline two\r"

    result = spine.perceive_text(
        source_id="test-source",
        text=native_text,
        transforms=("strip_utf8_bom", "normalize_newlines"),
    )

    assert Path(result.evidence.path).read_bytes().decode("utf-8") == native_text
    assert result.observation_text == "line one\nline two\n"
    assert result.receipt.acuity_status == AcuityStatus.RECOVERED.value
    assert result.receipt.transforms == ("strip_utf8_bom", "normalize_newlines")
    assert result.receipt.native_sha256 != result.receipt.observation_sha256
    assert result.receipt.exactness_class == ExactnessClass.NORMALIZED.value
    assert result.receipt.taint_labels == ("normalized_representation",)
    assert len(result.transformation_lineage) == 1
    assert result.transformation_lineage[0].receipt_sha256 == (
        result.receipt.transformation_lineage_sha256s[0]
    )
    assert "enhancement_does_not_increase_authority" in result.receipt.limitations


def test_unsupported_transform_is_quarantined_with_native_evidence(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-perception-quarantine")

    result = spine.perceive_text(
        source_id="operator",
        text="keep the native evidence",
        transforms=("invent_missing_words",),
    )

    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.receipt.acuity_status == AcuityStatus.UNAVAILABLE.value
    assert result.observation_text is None
    assert Path(result.evidence.path).read_text(encoding="utf-8") == "keep the native evidence"
    assert "unsupported_transform" in result.receipt.limitations


def test_perception_does_not_expand_authority(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
        task_id="task-perception-authority",
    )
    before = spine.core.authority

    result = spine.perceive_text(source_id="operator", text="read only")

    assert spine.core.authority == before
    assert result.packet.authority == before
    assert result.packet.authority.grants == ("artifact.write",)


def test_empty_source_is_degraded_not_fabricated(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="task-perception-empty")

    result = spine.perceive_text(source_id="empty-source", text="")

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.receipt.acuity_status == AcuityStatus.DEGRADED.value
    assert result.observation_text == ""
    assert "empty_source" in result.receipt.limitations
