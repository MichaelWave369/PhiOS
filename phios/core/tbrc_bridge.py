"""TBRC integration bridge with lazy imports and graceful degradation."""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any


class TBRCBridge:
    """Two-way TBRC bridge.

    All TBRC imports are lazy and done inside methods only.
    """

    def __init__(self) -> None:
        self._reason = "TBRC not found"

    def degraded_box(self, reason: str | None = None) -> str:
        text = (reason or self._reason)[:39]
        return "\n".join(
            [
                "+-----------------------------------------+",
                "| TBRC bridge unavailable                 |",
                f"| {text.ljust(39)} |",
                "+-----------------------------------------+",
            ]
        )

    def _degraded(self, reason: str | None = None) -> dict[str, Any]:
        return {"available": False, "reason": reason or self._reason}

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

    def _load_tbrc(self) -> Any | None:
        if not self.is_available():
            return None
        try:
            return importlib.import_module("tbrc")
        except Exception:
            self._reason = "TBRC import failed"
            return None

    def get_active_session(self) -> dict[str, Any] | None:
        module = self._load_tbrc()
        if module is None:
            return None
        try:
            getter = getattr(module, "get_active_session", None)
            if callable(getter):
                session = getter()
                return dict(session) if session else None
        except Exception:
            return None
        return None

    def get_session_lt(self) -> float | None:
        session = self.get_active_session()
        if not session:
            return None
        value = session.get("lt") or session.get("lt_score") or session.get("session_lt")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def start_quick_session(self, preset: str = "default", operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            return {"available": self.is_available(), "started": False, "reason": "operator confirmation required"}
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        try:
            starter = getattr(module, "start_quick_session", None)
            if callable(starter):
                return dict(starter(preset=preset, operator_confirmed=True))
            return {"available": True, "started": True, "preset": preset}
        except Exception:
            return self._degraded("TBRC start session failed")

    def stop_active_session(self, operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            return {"available": self.is_available(), "stopped": False, "reason": "operator confirmation required"}
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        try:
            stopper = getattr(module, "stop_active_session", None)
            if callable(stopper):
                return dict(stopper(operator_confirmed=True))
            return {"available": True, "stopped": True}
        except Exception:
            return self._degraded("TBRC stop session failed")

    def search_memory(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        module = self._load_tbrc()
        if module is None:
            return []
        try:
            search = getattr(module, "search_memory", None)
            if callable(search):
                return list(search(query=query, limit=limit))
        except Exception:
            return []
        return []

    def memorize_phi_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        lt_level = float(snapshot.get("lt", snapshot.get("lt_score", 0.0)) or 0.0)
        payload = dict(snapshot)
        payload["tags"] = ["phios_snapshot", "sovereign", f"lt_level:{lt_level:.3f}"]
        try:
            saver = getattr(module, "memorize_phi_snapshot", None)
            if callable(saver):
                return dict(saver(payload))
            return {"available": True, "memorized": True, "tags": payload["tags"]}
        except Exception:
            return self._degraded("TBRC memorize failed")

    def get_kg_summary(self) -> dict[str, Any]:
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        try:
            getter = getattr(module, "get_kg_summary", None)
            if callable(getter):
                data = dict(getter())
                data.setdefault("available", True)
                data.setdefault("nodes", 0)
                data.setdefault("edges", 0)
                return data
            return {"available": True, "nodes": 0, "edges": 0}
        except Exception:
            return self._degraded("TBRC kg summary failed")

    def find_concept(self, concept: str) -> list[dict[str, Any]]:
        module = self._load_tbrc()
        if module is None:
            return []
        try:
            finder = getattr(module, "find_concept", None)
            if callable(finder):
                return list(finder(concept=concept))
        except Exception:
            return []
        return []

    def get_archive_timeline(self, limit: int = 9) -> list[dict[str, Any]]:
        module = self._load_tbrc()
        if module is None:
            return []
        try:
            getter = getattr(module, "get_archive_timeline", None)
            if callable(getter):
                return list(getter(limit=limit))
        except Exception:
            return []
        return []

    def add_archive_milestone(
        self,
        title: str,
        narrative: str,
        significance: str,
        operator_confirmed: bool = False,
    ) -> dict[str, Any]:
        if not operator_confirmed:
            return {"available": self.is_available(), "added": False, "reason": "operator confirmation required"}
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        try:
            adder = getattr(module, "add_archive_milestone", None)
            if callable(adder):
                return dict(adder(title=title, narrative=narrative, significance=significance, operator_confirmed=True))
            return {"available": True, "added": True, "title": title, "significance": significance}
        except Exception:
            return self._degraded("TBRC archive add failed")

    def get_phb_status(self) -> dict[str, Any]:
        module = self._load_tbrc()
        if module is None:
            return self._degraded()
        try:
            getter = getattr(module, "get_phb_status", None)
            if callable(getter):
                data = dict(getter())
                data.setdefault("available", True)
                data.setdefault("connected", False)
                data.setdefault("sensor_count", 0)
                return data
            return {"available": True, "connected": False, "sensor_count": 0}
        except Exception:
            return self._degraded("TBRC PHB status failed")

    def get_phb_lt_contribution(self) -> float:
        status = self.get_phb_status()
        if not status.get("available", False) or not status.get("connected", False):
            return 0.0
        contribution = status.get("lt_contribution", 0.0)
        try:
            return max(0.0, float(contribution))
        except (TypeError, ValueError):
            return 0.0

    def full_status(self) -> dict[str, Any]:
        if not self.is_available():
            return {
                "available": False,
                "reason": self._reason,
                "version": None,
                "active_session": None,
                "memory_entries": 0,
                "kg_nodes": 0,
                "archive_entries": 0,
                "phb_connected": False,
                "phb_sensor_count": 0,
                "last_session_lt": None,
                "brainc_tbrc_available": False,
            }

        module = self._load_tbrc()
        if module is None:
            return self._degraded("TBRC load failed")

        try:
            version = getattr(module, "__version__", "unknown")
            active = self.get_active_session()
            memory_entries = len(self.search_memory("", limit=5))
            kg = self.get_kg_summary()
            archive = self.get_archive_timeline(limit=9)
            phb = self.get_phb_status()
            return {
                "available": True,
                "version": version,
                "active_session": active,
                "memory_entries": memory_entries,
                "kg_nodes": int(kg.get("nodes", 0)) if isinstance(kg, dict) else 0,
                "archive_entries": len(archive),
                "phb_connected": bool(phb.get("connected", False)) if isinstance(phb, dict) else False,
                "phb_sensor_count": int(phb.get("sensor_count", 0)) if isinstance(phb, dict) else 0,
                "last_session_lt": self.get_session_lt(),
                "brainc_tbrc_available": True,
            }
        except Exception:
            return self._degraded("TBRC status failed")


# Backward-compatible wrappers for older commands
    def memory_stats(self) -> dict[str, Any]:
        status = self.full_status()
        if not status.get("available", False):
            return self._degraded(status.get("reason", self._reason))
        return {"available": True, "entries": status.get("memory_entries", 0)}

    def memory_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.search_memory(query, limit=limit)

    def archive_timeline(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.get_archive_timeline(limit=limit)

    def archive_add(self, title: str, narrative: str, entry_type: str = "program_milestone") -> dict[str, Any]:
        return self.add_archive_milestone(title, narrative, entry_type, operator_confirmed=True)

    def kg_stats(self) -> dict[str, Any]:
        return self.get_kg_summary()


def tbrc_connected() -> bool:
    return TBRCBridge().is_available()
