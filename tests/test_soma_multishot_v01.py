from pathlib import Path

from phios.mandala import MandalaStatus
from phios.soma import CapturedFrame, ScreenCaptureError, ScreenRegion
from phios.spine.runtime import PhiOSSpine


class FakeBurstProvider:
    name = "fake-burst"

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


class FakeScorer:
    name = "fake-score-v1"

    def __init__(self, scores: dict[bytes, float]) -> None:
        self.scores = scores
        self.calls: list[bytes] = []

    def score(self, data: bytes) -> float:
        self.calls.append(data)
        return self.scores[data]


def _frame(data: bytes, *, width: int = 320, height: int = 200) -> CapturedFrame:
    return CapturedFrame(
        data=data,
        width=width,
        height=height,
        backend="fake-burst",
    )


def _spine(tmp_path: Path, *grants: str) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=grants,
        task_id="burst-test",
    )


def test_multishot_requires_separate_grant(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"a"), _frame(b"b")])
    scorer = FakeScorer({b"a": 1.0, b"b": 2.0})
    spine = _spine(tmp_path, "perception.screen.capture")

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "missing_grant:perception.screen.multishot" in result.receipt.limitations


def test_burst_selects_highest_scoring_native_frame(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"a"), _frame(b"b"), _frame(b"c")])
    scorer = FakeScorer({b"a": 1.0, b"b": 9.0, b"c": 4.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=10, y=20, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=3,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.valid_frames == 3
    assert len(result.frame_evidence) == 3
    assert all(Path(item.path).exists() for item in result.frame_evidence)
    selected = next(item for item in result.frame_evidence if Path(item.path).read_bytes() == b"b")
    assert result.selected_evidence_ref == selected.evidence_ref
    assert result.observation_sha256 == selected.sha256
    assert result.receipt.selection_method == "fake-score-v1"
    assert result.receipt.observation_evidence_ref == selected.evidence_ref
    assert "no_frame_fusion" in result.receipt.limitations


def test_score_tie_prefers_earliest_frame(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"first"), _frame(b"second")])
    scorer = FakeScorer({b"first": 5.0, b"second": 5.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
    )

    first = next(item for item in result.frame_evidence if Path(item.path).read_bytes() == b"first")
    assert result.selected_evidence_ref == first.evidence_ref


def test_partial_burst_is_degraded_but_can_select_valid_frame(tmp_path: Path) -> None:
    provider = FakeBurstProvider(
        [
            ScreenCaptureError("capture_failed", "one failed"),
            _frame(b"good"),
            _frame(b"better"),
        ]
    )
    scorer = FakeScorer({b"good": 3.0, b"better": 7.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=3,
    )

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.valid_frames == 2
    assert result.selected_evidence_ref is not None
    assert "partial_burst" in result.receipt.limitations


def test_all_capture_failures_produce_no_observation(tmp_path: Path) -> None:
    provider = FakeBurstProvider(
        [
            ScreenCaptureError("capture_failed", "one"),
            ScreenCaptureError("capture_failed", "two"),
        ]
    )
    scorer = FakeScorer({})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
    )

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.selected_evidence_ref is None
    assert result.observation_sha256 is None
    assert result.frame_evidence == ()


def test_mismatched_frame_is_preserved_but_not_selected(tmp_path: Path) -> None:
    provider = FakeBurstProvider(
        [
            _frame(b"wrong", width=319),
            _frame(b"good"),
        ]
    )
    scorer = FakeScorer({b"good": 2.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
    )

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert len(result.frame_evidence) == 2
    assert any(record["reason"] == "capture_dimensions_mismatch" for record in result.frame_records)
    selected = next(item for item in result.frame_evidence if Path(item.path).read_bytes() == b"good")
    assert result.selected_evidence_ref == selected.evidence_ref


def test_invalid_frame_count_is_blocked_before_capture(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"a")])
    scorer = FakeScorer({b"a": 1.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=1,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "invalid_frame_count" in result.receipt.limitations


def test_burst_total_pixel_budget_is_enforced(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"a"), _frame(b"b")])
    scorer = FakeScorer({b"a": 1.0, b"b": 2.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
        max_total_pixels=100,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "burst_too_large" in result.receipt.limitations


def test_multishot_does_not_expand_authority(tmp_path: Path) -> None:
    provider = FakeBurstProvider([_frame(b"a"), _frame(b"b")])
    scorer = FakeScorer({b"a": 1.0, b"b": 2.0})
    spine = _spine(
        tmp_path,
        "perception.screen.capture",
        "perception.screen.multishot",
    )
    before = spine.core.authority

    result = spine.perceive_screen_burst(
        region=ScreenRegion(x=0, y=0, width=320, height=200),
        provider=provider,
        scorer=scorer,
        frame_count=2,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
