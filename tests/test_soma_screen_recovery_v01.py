from pathlib import Path

from phios.mandala import MandalaStatus
from phios.soma import (
    AcuityStatus,
    CapturedFrame,
    ScreenCrop,
    ScreenRecoveryError,
    ScreenRecoveryFrames,
)
from phios.spine.runtime import PhiOSSpine


class FakeRecoveryProvider:
    name = "fake-recovery"

    def __init__(
        self,
        *,
        frames: ScreenRecoveryFrames | None = None,
        error: ScreenRecoveryError | None = None,
    ) -> None:
        self.frames = frames
        self.error = error
        self.calls = 0

    def recover(
        self,
        data: bytes,
        *,
        crop: ScreenCrop | None,
        scale: int,
        max_output_pixels: int,
    ) -> ScreenRecoveryFrames:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert data == b"native-screen"
        assert self.frames is not None
        return self.frames


def _native(spine: PhiOSSpine) -> str:
    evidence = spine.soma.evidence.put_bytes(
        b"native-screen",
        media_type="image/png",
        suffix=".png",
    )
    return evidence.evidence_ref


def _frame(data: bytes, width: int, height: int) -> CapturedFrame:
    return CapturedFrame(
        data=data,
        width=width,
        height=height,
        backend="fake-recovery",
    )


def test_recovery_requires_explicit_grant(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="recovery-denied")
    evidence_ref = _native(spine)
    provider = FakeRecoveryProvider(
        frames=ScreenRecoveryFrames(cropped=_frame(b"crop", 100, 50))
    )

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        crop=ScreenCrop(x=0, y=0, width=100, height=50),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert result.derived_evidence == ()
    assert "missing_grant:perception.screen.recover" in result.receipt.limitations


def test_tight_crop_preserves_native_and_creates_derived_evidence(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-crop",
    )
    evidence_ref = _native(spine)
    native_before = spine.soma.evidence.read_bytes(evidence_ref)
    provider = FakeRecoveryProvider(
        frames=ScreenRecoveryFrames(cropped=_frame(b"cropped-screen", 100, 50))
    )

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        crop=ScreenCrop(x=10, y=20, width=100, height=50),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.acuity_status == AcuityStatus.RECOVERED.value
    assert result.recovery_steps == ("tight_crop",)
    assert len(result.derived_evidence) == 1
    assert Path(result.derived_evidence[0].path).read_bytes() == b"cropped-screen"
    assert spine.soma.evidence.read_bytes(evidence_ref) == native_before
    assert result.receipt.native_evidence_ref == evidence_ref
    assert result.receipt.observation_evidence_ref == result.derived_evidence[0].evidence_ref


def test_crop_then_native_enlarge_records_chain(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-chain",
    )
    evidence_ref = _native(spine)
    provider = FakeRecoveryProvider(
        frames=ScreenRecoveryFrames(
            cropped=_frame(b"crop-stage", 80, 40),
            enlarged=_frame(b"enlarge-stage", 160, 80),
        )
    )

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        crop=ScreenCrop(x=5, y=5, width=80, height=40),
        scale=2,
        provider=provider,
    )

    assert result.recovery_steps == ("tight_crop", "native_enlarge_x2")
    assert len(result.derived_evidence) == 2
    assert result.receipt.derived_evidence_refs == tuple(
        item.evidence_ref for item in result.derived_evidence
    )
    assert result.receipt.observation_evidence_ref == result.derived_evidence[-1].evidence_ref
    assert result.receipt.derivation_chain[0]["input_evidence_ref"] == evidence_ref
    assert (
        result.receipt.derivation_chain[1]["input_evidence_ref"]
        == result.derived_evidence[0].evidence_ref
    )
    assert result.receipt.derivation_chain[1]["method"] == "nearest_neighbor_pixel_replication"


def test_no_recovery_request_is_blocked_without_reading_provider(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-none",
    )
    evidence_ref = _native(spine)
    provider = FakeRecoveryProvider()

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "no_recovery_requested" in result.receipt.limitations
    assert provider.calls == 0


def test_missing_native_evidence_is_blocked(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-missing",
    )
    provider = FakeRecoveryProvider()

    result = spine.recover_screen_evidence(
        evidence_ref="evidence:sha256:" + "a" * 64,
        scale=2,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "native_evidence_unavailable" in result.receipt.limitations
    assert provider.calls == 0


def test_provider_boundary_failure_never_promotes_derived_observation(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-bounds",
    )
    evidence_ref = _native(spine)
    provider = FakeRecoveryProvider(
        error=ScreenRecoveryError("crop_out_of_bounds", "bad crop")
    )

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        crop=ScreenCrop(x=10, y=10, width=100, height=50),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.receipt.native_preserved is True
    assert result.observation_evidence_ref is None
    assert "no_derived_observation_promoted" in result.receipt.limitations


def test_invalid_scale_is_blocked_before_evidence_read(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-scale",
    )
    evidence_ref = _native(spine)
    provider = FakeRecoveryProvider()

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        scale=5,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "invalid_scale" in result.receipt.limitations
    assert provider.calls == 0


def test_recovery_does_not_expand_authority(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.recover"],
        task_id="recovery-authority",
    )
    evidence_ref = _native(spine)
    before = spine.core.authority
    provider = FakeRecoveryProvider(
        frames=ScreenRecoveryFrames(enlarged=_frame(b"enlarged", 640, 400))
    )

    result = spine.recover_screen_evidence(
        evidence_ref=evidence_ref,
        scale=2,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
