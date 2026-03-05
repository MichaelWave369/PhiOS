"""PhiOS notification utilities with graceful local fallback."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class NotificationEvent:
    kind: str
    title: str
    body: str
    timestamp: float


class PhiNotifier:
    """Emit local desktop notifications while preserving in-memory history."""

    MIN_INTERVAL = 9.0

    def __init__(self) -> None:
        self.history: deque[NotificationEvent] = deque(maxlen=9)
        self._last_sent: dict[str, float] = {}

    def notify(self, kind: str, title: str, body: str, timeout_ms: int = 2000, force: bool = False) -> bool:
        now = time.time()
        last = self._last_sent.get(kind, 0.0)
        if not force and now - last < self.MIN_INTERVAL:
            return False

        self._last_sent[kind] = now
        self.history.append(NotificationEvent(kind=kind, title=title, body=body, timestamp=now))

        binary = shutil.which("notify-send")
        if not binary:
            return True

        try:
            subprocess.run(
                [binary, title, body, "-t", str(timeout_ms)],
                check=False,
                capture_output=True,
                text=True,
            )
            return True
        except OSError:
            return True

    def coherence_alert(self, lt_score: float, delta: float, force: bool = False) -> bool:
        if delta <= 0.1:
            return False
        title = "PhiOS Coherence Alert"
        body = f"L(t) dropped by {delta:.3f}. Current L(t): {lt_score:.3f}."
        return self.notify("coherence_alert", title, body, timeout_ms=2500, force=force)

    def resonance_moment(self, lt_score: float, force: bool = False) -> bool:
        title = "PhiOS Resonance 369"
        body = f"Resonance moment reached. L(t): {lt_score:.3f}."
        return self.notify("resonance_369", title, body, timeout_ms=3000, force=force)

    def sovereignty_changed(self, active: bool, force: bool = False) -> bool:
        if active:
            title = "Sovereignty Enabled"
            body = "Sovereignty mode ON. Local agency is active."
        else:
            title = "Sovereignty Disabled"
            body = "Sovereignty mode OFF. Re-enable when ready."
        return self.notify("sovereignty", title, body, timeout_ms=2200, force=force)

    def session_rhythm(self, interval: int, force: bool = False) -> bool:
        if interval == 9:
            title = "Rhythm Aligned"
            body = "9-beat checkpoint reached. Gold coherence channel stabilized."
        elif interval == 6:
            title = "Rhythm Marker 6"
            body = "6-beat cadence marker reached."
        else:
            title = "Rhythm Marker 3"
            body = "3-beat cadence marker reached."
        return self.notify("session_rhythm", title, body, timeout_ms=1800, force=force)

    def status(self) -> dict[str, object]:
        return {
            "notify_send_available": bool(shutil.which("notify-send")),
            "last_notification_ts": max((event.timestamp for event in self.history), default=None),
            "history_count": len(self.history),
        }

    def history_lines(self) -> list[str]:
        return [f"{event.kind}: {event.title} - {event.body}" for event in self.history]
