"""PhiOS ↔ TBRC sync bridge functions."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from phios.core.tbrc_bridge import TBRCBridge


class SyncReport(TypedDict, total=False):
    available: bool
    action: str
    reason: str
    phios_snapshot_count: int
    tbrc_memory_count: int
    archive_entries: int
    kg_nodes: int
    pushed: int
    pulled_archive: int
    pulled_memory: int


def _snapshot_files() -> list[Path]:
    return sorted(Path.cwd().glob("phi_snapshot*.json"))


def sync_status() -> SyncReport:
    bridge = TBRCBridge()
    if not bridge.is_available():
        return {"available": False, "action": "status", "reason": "TBRC not available"}

    memory = bridge.memory_stats()
    archive = bridge.archive_timeline(limit=100)
    kg = bridge.kg_stats()
    return {
        "available": True,
        "action": "status",
        "phios_snapshot_count": len(_snapshot_files()),
        "tbrc_memory_count": int(memory.get("count", 0)) if isinstance(memory, dict) else 0,
        "archive_entries": len(archive),
        "kg_nodes": int(kg.get("nodes", 0)) if isinstance(kg, dict) else 0,
    }


def sync_push() -> SyncReport:
    bridge = TBRCBridge()
    if not bridge.is_available():
        return {"available": False, "action": "push", "reason": "TBRC not available"}

    pushed = 0
    for snap in _snapshot_files():
        result = bridge.archive_add(
            title=f"PhiOS Snapshot {snap.stem}",
            narrative=snap.read_text(encoding="utf-8"),
            entry_type="phios_snapshot",
        )
        if result.get("available", True):
            pushed += 1
    return {"available": True, "action": "push", "pushed": pushed}


def sync_pull() -> SyncReport:
    bridge = TBRCBridge()
    if not bridge.is_available():
        return {"available": False, "action": "pull", "reason": "TBRC not available"}

    archive = bridge.archive_timeline(limit=5)
    memory = bridge.memory_search("", limit=5)
    return {
        "available": True,
        "action": "pull",
        "pulled_archive": len(archive),
        "pulled_memory": len(memory),
    }


def sync_both() -> SyncReport:
    push = sync_push()
    pull = sync_pull()
    if not push.get("available", False) or not pull.get("available", False):
        return {"available": False, "action": "both", "reason": "TBRC not available"}
    return {
        "available": True,
        "action": "both",
        "pushed": int(push.get("pushed", 0)),
        "pulled_archive": int(pull.get("pulled_archive", 0)),
        "pulled_memory": int(pull.get("pulled_memory", 0)),
    }
