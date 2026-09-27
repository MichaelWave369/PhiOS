from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from phios.macro_ghostwalk import GhostWalkRecorder
from phios.macro_ghostwalk_capture import (
    CaptureStatus,
    GhostWalkCaptureAdapter,
    PointerClickEvent,
)
from phios.macro_ghostwalk_listener import (
    GhostWalkListenerBridge,
    GhostWalkListenerContractError,
    LLMHF_INJECTED,
    LLMHF_LOWER_IL_INJECTED,
    RawMouseHookEvent,
    WindowsGhostWalkListener,
)
from phios.macro_interaction_guard import WindowFrame
from phios.spine.ledger import RealityLedger

TITLE = "e" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame() -> WindowFrame:
    return WindowFrame(
        process_id="pid:5150",
        window_title_sha256=TITLE,
        left_px=100,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=True,
        captured_at="2026-09-27T01:20:00+00:00",
    )


class StaticWindowProvider:
    provider_id = "test.listener-window"

    def __init__(self) -> None:
        self.calls = 0

    def frame_for_click(
        self,
        event: PointerClickEvent,
    ) -> WindowFrame | None:
        self.calls += 1
        return _frame()


def _start_session(ledger: RealityLedger, session_id: str) -> None:
    GhostWalkRecorder(ledger).start(
        session_id=session_id,
        recorder_id="operator:mikey",
        started_at="2026-09-27T01:20:00+00:00",
    )


def _bridge(
    ledger: RealityLedger,
    *,
    listener_id: str = "listener:windows",
    provider: StaticWindowProvider | None = None,
) -> tuple[GhostWalkListenerBridge, StaticWindowProvider]:
    window = provider or StaticWindowProvider()
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=window,
    )
    return (
        GhostWalkListenerBridge(
            ledger=ledger,
            capture_adapter=adapter,
            listener_id=listener_id,
        ),
        window,
    )


def _raw(
    *,
    flags: int = 0,
    x: int = 500,
    y: int = 350,
    hook_time_ms: int = 12345,
    extra_info: int = 0,
) -> RawMouseHookEvent:
    return RawMouseHookEvent(
        x_px=x,
        y_px=y,
        flags=flags,
        hook_time_ms=hook_time_ms,
        extra_info=extra_info,
    )


def test_listener_001_human_left_click_flows_into_v014(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-human")
    bridge, window = _bridge(ledger)

    outcome = bridge.observe_left_button(
        session_id="ghost:listener-human",
        raw_event=_raw(),
        observed_at="2026-09-27T01:20:01+00:00",
    )

    assert outcome.receipt.listener_sequence == 0
    assert outcome.receipt.injected is False
    assert outcome.receipt.capture_status is CaptureStatus.RECORDED
    assert outcome.pointer_event.injected is False
    assert outcome.capture_outcome.observation is not None
    assert window.calls == 1

    observations = GhostWalkRecorder(ledger).observations(
        session_id="ghost:listener-human"
    )
    assert len(observations) == 1
    assert (
        outcome.receipt.capture_receipt_sha256
        == outcome.capture_outcome.receipt.receipt_sha256
    )


@pytest.mark.parametrize(
    ("flags", "lower"),
    [
        (LLMHF_INJECTED, False),
        (LLMHF_LOWER_IL_INJECTED, True),
        (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED, True),
    ],
)
def test_listener_002_windows_injection_flags_are_preserved_and_held(
    tmp_path: Path,
    flags: int,
    lower: bool,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, f"ghost:listener-injected:{flags}")
    bridge, window = _bridge(
        ledger,
        listener_id=f"listener:injected:{flags}",
    )
    raw = _raw(flags=flags)

    outcome = bridge.observe_left_button(
        session_id=f"ghost:listener-injected:{flags}",
        raw_event=raw,
        observed_at="2026-09-27T01:20:02+00:00",
    )

    assert raw.injected is True
    assert raw.lower_integrity_injected is lower
    assert outcome.pointer_event.injected is True
    assert outcome.receipt.injected is True
    assert outcome.receipt.lower_integrity_injected is lower
    assert outcome.receipt.capture_status is CaptureStatus.HELD
    assert outcome.capture_outcome.observation is None
    assert window.calls == 0


def test_listener_003_sequence_reanchors_after_bridge_restart(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-restart")

    first_bridge, _ = _bridge(
        ledger,
        listener_id="listener:restart",
    )
    first = first_bridge.observe_left_button(
        session_id="ghost:listener-restart",
        raw_event=_raw(hook_time_ms=1),
        observed_at="2026-09-27T01:20:03+00:00",
    )

    second_bridge, _ = _bridge(
        ledger,
        listener_id="listener:restart",
    )
    second = second_bridge.observe_left_button(
        session_id="ghost:listener-restart",
        raw_event=_raw(hook_time_ms=2),
        observed_at="2026-09-27T01:20:04+00:00",
    )

    assert first.receipt.listener_sequence == 0
    assert second.receipt.listener_sequence == 1
    assert ledger.next_ghostwalk_listener_sequence(
        listener_id="listener:restart"
    ) == 2


def test_listener_004_event_identity_is_deterministic_for_same_inputs(
    tmp_path: Path,
) -> None:
    ledger_a = RealityLedger(tmp_path / "a" / "receipts.jsonl")
    ledger_b = RealityLedger(tmp_path / "b" / "receipts.jsonl")
    _start_session(ledger_a, "ghost:deterministic")
    _start_session(ledger_b, "ghost:deterministic")
    bridge_a, _ = _bridge(
        ledger_a,
        listener_id="listener:deterministic",
    )
    bridge_b, _ = _bridge(
        ledger_b,
        listener_id="listener:deterministic",
    )
    raw = _raw(hook_time_ms=77, extra_info=99)

    a = bridge_a.observe_left_button(
        session_id="ghost:deterministic",
        raw_event=raw,
        observed_at="2026-09-27T01:20:05+00:00",
    )
    b = bridge_b.observe_left_button(
        session_id="ghost:deterministic",
        raw_event=raw,
        observed_at="2026-09-27T01:20:05+00:00",
    )

    assert a.pointer_event.event_id == b.pointer_event.event_id
    assert a.pointer_event.event_sha256 == b.pointer_event.event_sha256
    assert a.receipt.receipt_sha256 == b.receipt.receipt_sha256


def test_listener_005_persisted_sequence_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-tamper")
    bridge, _ = _bridge(
        ledger,
        listener_id="listener:tamper",
    )
    bridge.observe_left_button(
        session_id="ghost:listener-tamper",
        raw_event=_raw(),
        observed_at="2026-09-27T01:20:06+00:00",
    )

    path = tmp_path / "ledger" / "ghostwalk-listener-receipts.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["listener_sequence"] = 9
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="listener sequences are not contiguous",
    ):
        ledger.next_ghostwalk_listener_sequence(
            listener_id="listener:tamper"
        )


def test_listener_006_listener_receipt_is_persisted_and_zero_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-receipt")
    bridge, _ = _bridge(
        ledger,
        listener_id="listener:receipt",
    )
    outcome = bridge.observe_left_button(
        session_id="ghost:listener-receipt",
        raw_event=_raw(),
        observed_at="2026-09-27T01:20:07+00:00",
    )

    rows = ledger.ghostwalk_listener_receipts(
        listener_id="listener:receipt"
    )
    assert rows[0]["receipt_sha256"] == outcome.receipt.receipt_sha256
    assert outcome.receipt.operational_authority is False
    assert outcome.receipt.action_authority is False
    assert outcome.receipt.execution_authority is False
    assert ledger.recent() == []


def test_listener_007_windows_listener_rejects_non_windows(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-platform")
    bridge, _ = _bridge(ledger)

    with pytest.raises(
        GhostWalkListenerContractError,
        match="requires Windows",
    ):
        WindowsGhostWalkListener(bridge=bridge)


def test_listener_008_raw_hook_event_is_zero_authority() -> None:
    raw = _raw()
    assert raw.operational_authority is False
    assert raw.action_authority is False
    assert raw.execution_authority is False
    assert len(raw.raw_event_sha256) == 64


def test_listener_009_tampered_prior_receipt_hash_fails_before_next_event(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:listener-hash-tamper")
    bridge, _ = _bridge(
        ledger,
        listener_id="listener:hash-tamper",
    )
    bridge.observe_left_button(
        session_id="ghost:listener-hash-tamper",
        raw_event=_raw(),
        observed_at="2026-09-27T01:20:08+00:00",
    )

    path = tmp_path / "ledger" / "ghostwalk-listener-receipts.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["observed_at"] = "2026-09-27T01:20:09+00:00"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkListenerContractError,
        match="listener receipt hash mismatch",
    ):
        bridge.observe_left_button(
            session_id="ghost:listener-hash-tamper",
            raw_event=_raw(hook_time_ms=999),
            observed_at="2026-09-27T01:20:10+00:00",
        )
