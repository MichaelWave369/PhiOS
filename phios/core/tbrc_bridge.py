"""TBRC bridge placeholder."""

from __future__ import annotations

import os
from pathlib import Path


def tbrc_connected() -> bool:
    tbrc_path = os.environ.get("TBRC_PATH")
    if tbrc_path and Path(tbrc_path).exists():
        return True
    try:
        __import__("tbrc")
        return True
    except Exception:
        return False
