"""Timing utilities."""

from __future__ import annotations

import time


def monotonic_seconds() -> float:
    return time.monotonic()
