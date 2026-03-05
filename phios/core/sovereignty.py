"""Sovereign export/verify utilities."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios import __version__
from phios.core.lt_engine import compute_lt


MANIFESTO_LINK = "https://enterthefield.org/phios"


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def export_snapshot(path: str) -> Path:
    snapshot = {
        "schema": "v0.1.phios_export",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "system": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": __import__("os").cpu_count(),
        },
        "last_lt": compute_lt(),
        "manifesto_link": MANIFESTO_LINK,
    }
    digest = _stable_hash(snapshot)
    snapshot["sha256"] = digest
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return out_path


def verify_snapshot(path: str) -> tuple[bool, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Unable to read export: {exc}"

    if "sha256" not in data:
        return False, "Missing sha256 field"

    given = data.pop("sha256")
    expected = _stable_hash(data)
    if given == expected:
        return True, "Hash matches"
    return False, "Hash mismatch"
