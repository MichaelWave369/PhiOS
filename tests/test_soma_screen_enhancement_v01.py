from pathlib import Path

from phios.mandala import MandalaStatus
from phios.soma import (
    AcuityStatus,
    EnhancedFrame,
    ScreenEnhancementError,
    ScreenEnhancementSpec,
)
from phios.spine.runtime import PhiOSSpine


class FakeEnhancementProvider:
    name = "fake-unsharp-v1"

    def __init__(
        self,
        *,
        frame: EnhancedFrame | None = None,
        error: ScreenEnhancementError | None = None,
    ) -> None:
        self.frame = frame
        self.error = error
        self.calls = 0

    def enhance(
        self,
        data: bytes,
        *,
        spec: ScreenEnhancementSpec,
    ) -> EnhancedFrame:
        self.calls += 1
        assert data == b"source-png"
        if self.error is not None:
            raise self.error
        assert self.frame is not None
        return self.frame


def _source(spine: PhiOSSpine) -> str:
    evidence = spine.soma.evidence.put_bytes(
        b"source-png",
        media_type="image/png",
        suffix=".png",
    )
    return evidence.evidence_ref


def _frame(
    data: bytes = b"enhanced-png",
    *,
    input_width: int = 320,
    input_height: int = 200,
    output_width: int = 320,
    output_height: int = 200,
) -> EnhancedFrame:
    return EnhancedFrame(
        data=data,
        input_width=input_width,
        input_height=input_height,
        output_width=output_width,
        output_height=output_height,
        backend="fake-unsharp-v1",
    )


def test_enhancement_requires_explicit_grant(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="enhance-denied")
    ref = _source(spine)
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert result.derived_evidence is None
    assert "missing_grant:perception.screen.enhance" in result.receipt.limitations


def test_valid_sharpening_preserves_source_and_creates_derived(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-ok",
    )
    ref = _source(spine)
    before = spine.soma.evidence.read_bytes(ref)
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
        spec=ScreenEnhancementSpec(radius=1.25, percent=180, threshold=2),
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.acuity_status == AcuityStatus.RECOVERED.value
    assert result.derived_evidence is not None
    assert Path(result.derived_evidence.path).read_bytes() == b"enhanced-png"
    assert spine.soma.evidence.read_bytes(ref) == before
    assert result.receipt.input_evidence_ref == ref
    assert result.receipt.observation_evidence_ref == result.derived_evidence.evidence_ref
    assert result.receipt.enhancement_method == "unsharp_mask"
    assert "enhancement_does_not_recover_lost_information" in result.receipt.limitations


def test_enhancement_records_derivation_chain(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-chain",
    )
    ref = _source(spine)
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.derived_evidence is not None
    step = result.receipt.derivation_chain[0]
    assert step["input_evidence_ref"] == ref
    assert step["output_evidence_ref"] == result.derived_evidence.evidence_ref
    assert step["method"] == "unsharp_mask"
    assert result.receipt.enhancement_backend == "fake-unsharp-v1"


def test_invalid_parameters_are_blocked_before_evidence_read(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-invalid",
    )
    ref = _source(spine)
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
        spec=ScreenEnhancementSpec(percent=999),
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "invalid_percent" in result.receipt.limitations


def test_missing_source_evidence_is_blocked(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-missing",
    )
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref="evidence:sha256:" + "a" * 64,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "source_evidence_unavailable" in result.receipt.limitations


def test_decode_failure_is_quarantined_without_derivative(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-decode",
    )
    ref = _source(spine)
    provider = FakeEnhancementProvider(
        error=ScreenEnhancementError("enhancement_decode_failed", "bad image")
    )

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.derived_evidence is None
    assert result.observation_evidence_ref is None
    assert "no_derived_observation_promoted" in result.receipt.limitations


def test_dimension_change_is_preserved_but_not_promoted(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-dimensions",
    )
    ref = _source(spine)
    provider = FakeEnhancementProvider(
        frame=_frame(output_width=640, output_height=400)
    )

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.derived_evidence is not None
    assert Path(result.derived_evidence.path).read_bytes() == b"enhanced-png"
    assert result.observation_evidence_ref is None
    assert "enhancement_dimensions_changed" in result.receipt.limitations


def test_enhancement_does_not_expand_authority(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.enhance"],
        task_id="enhance-authority",
    )
    ref = _source(spine)
    before = spine.core.authority
    provider = FakeEnhancementProvider(frame=_frame())

    result = spine.enhance_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
