from pathlib import Path

from phios.mandala import MandalaStatus
from phios.soma import (
    AcuityStatus,
    CapturedFrame,
    ScreenCaptureError,
    ScreenRegion,
)
from phios.spine.runtime import PhiOSSpine


class FakeProvider:
    name = "fake-screen"

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def capture(self, region: ScreenRegion) -> CapturedFrame:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, CapturedFrame)
        return outcome


def _frame(data: bytes = b"native-png") -> CapturedFrame:
    return CapturedFrame(
        data=data,
        width=320,
        height=200,
        backend="fake-screen",
    )


def test_screen_capture_is_denied_without_explicit_grant(tmp_path: Path) -> None:
    provider = FakeProvider([_frame()])
    spine = PhiOSSpine(state_root=tmp_path, task_id="screen-denied")

    result = spine.perceive_screen(
        region=ScreenRegion(x=10, y=20, width=320, height=200),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.evidence is None
    assert provider.calls == 0
    assert "missing_grant:perception.screen.capture" in result.receipt.limitations


def test_screen_capture_preserves_native_frame(tmp_path: Path) -> None:
    provider = FakeProvider([_frame(b"frame-one")])
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-ok",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=10, y=20, width=320, height=200),
        provider=provider,
    )

    assert result.evidence is not None
    assert Path(result.evidence.path).read_bytes() == b"frame-one"
    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.acuity_status == AcuityStatus.NATIVE.value
    assert result.receipt.capture_region == {
        "x": 10,
        "y": 20,
        "width": 320,
        "height": 200,
    }
    assert result.receipt.capture_attempts == 1
    assert result.receipt.recovery_steps == ()
    assert result.observation_sha256 == result.evidence.sha256


def test_screen_reacquire_recovers_after_first_failure(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            ScreenCaptureError("capture_failed", "first attempt failed"),
            _frame(b"second-frame"),
        ]
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-recovered",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        reacquire_attempts=1,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.acuity_status == AcuityStatus.RECOVERED.value
    assert result.capture_attempts == 2
    assert result.receipt.recovery_steps == ("reacquire_same_region",)


def test_invalid_region_is_blocked_before_capture(tmp_path: Path) -> None:
    provider = FakeProvider([_frame()])
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-invalid-region",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=0, y=0, width=0, height=200),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "invalid_region" in result.receipt.limitations
    assert provider.calls == 0


def test_region_pixel_budget_is_enforced(tmp_path: Path) -> None:
    provider = FakeProvider([_frame()])
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-budget",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        max_pixels=10,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "region_too_large" in result.receipt.limitations
    assert provider.calls == 0


def test_capture_failure_is_degraded_not_fabricated(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            ScreenCaptureError("capture_failed", "one"),
            ScreenCaptureError("capture_failed", "two"),
        ]
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-unavailable",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        reacquire_attempts=1,
    )

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.receipt.acuity_status == AcuityStatus.UNAVAILABLE.value
    assert result.evidence is None
    assert result.observation_sha256 is None
    assert "no_observation_fabricated" in result.receipt.limitations


def test_dimension_mismatch_preserves_frame_but_quarantines_it(tmp_path: Path) -> None:
    bad = CapturedFrame(
        data=b"mismatched-frame",
        width=321,
        height=200,
        backend="fake-screen",
    )
    provider = FakeProvider([bad])
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-mismatch",
    )

    result = spine.perceive_screen(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        reacquire_attempts=0,
    )

    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.evidence is not None
    assert Path(result.evidence.path).read_bytes() == b"mismatched-frame"
    assert "capture_dimensions_mismatch" in result.receipt.limitations
    assert result.observation_sha256 is None


def test_screen_perception_does_not_expand_authority(tmp_path: Path) -> None:
    provider = FakeProvider([_frame()])
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.screen.capture"],
        task_id="screen-authority",
    )
    before = spine.core.authority

    result = spine.perceive_screen(
        region=ScreenRegion(x=-100, y=50, width=320, height=200),
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
