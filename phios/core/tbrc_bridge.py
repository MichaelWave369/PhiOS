"""TBRC bridge placeholder with lazy imports."""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any


class TBRCBridge:
    def __init__(self) -> None:
        self._reason = "TBRC not found"

    def is_available(self) -> bool:
        try:
            tbrc_path = os.environ.get("TBRC_PATH")
            if tbrc_path and Path(tbrc_path).exists():
                return True
            found = importlib.util.find_spec("tbrc") is not None
            if not found:
                self._reason = "TBRC module not installed"
            return found
        except Exception:
            self._reason = "TBRC probe failed"
            return False

    def _degraded_stats(self) -> dict[str, Any]:
        return {"available": False, "reason": self._reason}

    def memory_stats(self) -> dict[str, Any]:
        if not self.is_available():
            return self._degraded_stats()
        try:
            module = importlib.import_module("tbrc")
            getter = getattr(module, "memory_stats", None)
            if callable(getter):
                return dict(getter())
            return {"available": True}
        except Exception:
            return self._degraded_stats()

    def memory_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            module = importlib.import_module("tbrc")
            search = getattr(module, "memory_search", None)
            if callable(search):
                return list(search(query=query, limit=limit))
            return []
        except Exception:
            return []

    def archive_timeline(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            module = importlib.import_module("tbrc")
            getter = getattr(module, "archive_timeline", None)
            if callable(getter):
                return list(getter(limit=limit))
            return []
        except Exception:
            return []

    def archive_add(self, title: str, narrative: str, entry_type: str = "program_milestone") -> dict[str, Any]:
        if not self.is_available():
            return self._degraded_stats()
        try:
            module = importlib.import_module("tbrc")
            add = getattr(module, "archive_add", None)
            if callable(add):
                return dict(add(title=title, narrative=narrative, entry_type=entry_type))
            return {"available": True, "title": title, "entry_type": entry_type}
        except Exception:
            return self._degraded_stats()

    def kg_stats(self) -> dict[str, Any]:
        if not self.is_available():
            return self._degraded_stats()
        try:
            module = importlib.import_module("tbrc")
            getter = getattr(module, "kg_stats", None)
            if callable(getter):
                return dict(getter())
            return {"available": True}
        except Exception:
            return self._degraded_stats()


def tbrc_connected() -> bool:
    return TBRCBridge().is_available()
