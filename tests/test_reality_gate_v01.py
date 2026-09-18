from pathlib import Path

from phios.mandala import MandalaStatus
from phios.reality import RealityClaim, RealityClaimKind, RealityVerdict
from phios.spine.runtime import PhiOSSpine


def _text_evidence(spine: PhiOSSpine, text: str) -> str:
    return spine.soma.evidence.put_text(text).evidence_ref


def test_reality_verification_requires_explicit_grant(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="reality-denied")
    ref = _text_evidence(spine, "PORT 24 DOWN")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["verdict"] == RealityVerdict.BLOCKED.value
    assert result.receipt.evidence_used == ()
    assert "missing_grant:reality.verify" in result.receipt.limitations


def test_source_content_claim_can_be_supported(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-supported",
    )
    ref = _text_evidence(spine, "Switch report:\nPORT 24   DOWN\n")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited OCR text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="port 24 down",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.SUPPORTED.value
    assert result.claim_results[0]["matched_evidence_ref"] == ref
    assert result.receipt.evidence_used == (ref,)
    assert result.receipt.promotion_status == "not_promoted"


def test_source_content_absence_is_disputed(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-disputed",
    )
    ref = _text_evidence(spine, "PORT 24 UP")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.CONTRADICTED.value
    assert result.receipt.unresolved_contradictions == (claim.claim_id,)


def test_world_state_is_not_laundered_from_ocr_text(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-world",
    )
    ref = _text_evidence(spine, "PORT 24 DOWN")
    claim = RealityClaim.create(
        kind=RealityClaimKind.WORLD_STATE,
        statement="Physical switch port 24 is currently down.",
        evidence_refs=(ref,),
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert (
        result.claim_results[0]["reason"]
        == "world_state_requires_independent_world_verifier"
    )
    assert result.receipt.evidence_used == ()
    assert claim.claim_id in result.receipt.unresolved_claims


def test_world_state_with_no_evidence_remains_unresolved(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-world-empty",
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.WORLD_STATE,
        statement="Physical switch port 24 is currently down.",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value


def test_unreadable_source_evidence_is_unresolved(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-unreadable",
    )
    ref = spine.soma.evidence.put_bytes(
        b"\xff\xfe\x00",
        media_type="application/octet-stream",
        suffix=".bin",
    ).evidence_ref
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="Binary evidence contains a phrase.",
        evidence_refs=(ref,),
        expected_text="phrase",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.receipt.evidence_used == ()


def test_mixed_supported_and_world_state_claims_remain_unknown(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-mixed",
    )
    ref = _text_evidence(spine, "PORT 24 DOWN")
    source_claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )
    world_claim = RealityClaim.create(
        kind=RealityClaimKind.WORLD_STATE,
        statement="Physical switch port 24 is currently down.",
        evidence_refs=(ref,),
    )

    result = spine.verify_reality(claims=(source_claim, world_claim))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.receipt.verdict_summary == {
        RealityVerdict.SUPPORTED.value: 1,
        RealityVerdict.UNRESOLVED.value: 1,
    }


def test_invalid_source_claim_is_blocked(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-invalid",
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="Missing required contract fields.",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["verdict"] == RealityVerdict.BLOCKED.value
    assert "source_claim_requires_evidence" in result.receipt.limitations
    assert "source_claim_requires_expected_text" in result.receipt.limitations


def test_reality_verification_does_not_expand_authority(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-authority",
    )
    ref = _text_evidence(spine, "PORT 24 DOWN")
    before = spine.core.authority
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before


def test_reality_receipt_follows_gate_receipt(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="reality-ledger",
    )
    ref = _text_evidence(spine, "PORT 24 DOWN")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )

    spine.verify_reality(claims=(claim,))

    receipts = spine.mandala_ledger.recent(2)
    assert receipts[0]["receipt_type"] == "GateReceipt"
    assert receipts[1]["receipt_type"] == "RealityReceipt"
