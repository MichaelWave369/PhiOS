"""PhiOS Bioeffector Layer.

Boundary contract:
- Bioeffector tracking is a PhiOS workflow/observatory feature.
- PhiKernel remains the runtime source-of-truth for anchor/heart/coherence/capsules/router safety.
- Entries here are operator notes and symbolic session support context, not medical advice.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _config_root() -> Path:
    root = Path(os.environ.get("PHIOS_CONFIG_HOME", str(Path.home())))
    return root / ".phi"


def _store_path() -> Path:
    return _config_root() / "bioeffectors.json"


def _validate_export_path(path_str: str) -> Path:
    target = Path(path_str).expanduser()
    if target.suffix.lower() != ".json":
        raise ValueError("Export path must end with .json")
    if ".." in target.parts:
        raise ValueError("Export path may not contain '..' path parts")
    resolved = target.resolve(strict=False)
    if resolved.is_dir():
        raise ValueError("Export path points to a directory")
    return resolved


def _load_entries() -> list[dict[str, object]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _save_entries(entries: list[dict[str, object]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def list_bioeffectors() -> list[dict[str, object]]:
    return _load_entries()


def add_bioeffector_entry(
    *,
    name: str,
    compound: str,
    source: str,
    dose: str | None = None,
    unit: str | None = None,
    timing: str | None = None,
    notes: str | None = None,
    formula: str | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "entry_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "compound": compound,
        "source": source,
        "formula": formula,
        "dose": dose,
        "unit": unit,
        "timing": timing,
        "notes": notes,
    }
    entries = _load_entries()
    entries.append(entry)
    _save_entries(entries)
    return entry


def summarize_bioeffectors() -> dict[str, object]:
    entries = _load_entries()
    recent_entries = entries[-5:]
    sources = [str(e.get("source", "unknown")) for e in entries if e.get("source")]
    timings = [str(e.get("timing", "")) for e in entries if e.get("timing")]

    dominant_source_type = Counter(sources).most_common(1)[0][0] if sources else "none"
    timing_state = "unspecified"
    if timings:
        timing_state = "coordinated" if len(set(timings)) == 1 else "mixed"

    support_vector = "active_support" if len(entries) >= 2 else "baseline"
    tracking_confidence = "high" if len(entries) >= 3 else "moderate" if entries else "low"
    session_correlation_readiness = "ready" if len(entries) >= 2 and timing_state != "unspecified" else "forming"

    return {
        "bioeffector_count": len(entries),
        "recent_entries": recent_entries,
        "dominant_source_type": dominant_source_type,
        "timing_state": timing_state,
        "bioeffector_mode": "tracking-observatory",
        "support_vector": support_vector,
        "tracking_confidence": tracking_confidence,
        "session_correlation_readiness": session_correlation_readiness,
    }


def export_bioeffector_bundle(path_str: str) -> Path:
    target = _validate_export_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_entries()
    summary = summarize_bioeffectors()
    payload: dict[str, Any] = {
        "metadata": {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "PhiOS Bioeffector Layer",
        },
        "entries": entries,
        "summary": summary,
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
