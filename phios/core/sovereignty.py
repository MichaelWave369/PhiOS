"""Sovereign export/verify utilities with typed snapshot schema."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict, cast

from phios.core.brainc_client import ollama_available
from phios.core.lt_engine import LtResultDict
from phios.core.tbrc_bridge import TBRCBridge

MANIFESTO_LINK = "https://enterthefield.org/phios"


class SnapshotSystem(TypedDict):
    hostname: str
    os: str
    python: str
    cpu_count: int | None


class SnapshotCoherence(TypedDict):
    lt_score: float
    a_on: float
    psi_b: float
    g_score: float
    c_score: float
    trajectory: str
    history: list[float]


class SnapshotSovereignty(TypedDict):
    mode_active: bool
    external_connections_blocked: bool


class SnapshotSession(TypedDict):
    duration_s: int
    commands_run: int
    resonance_moments_hit: int
    rhythm_position: Literal["3", "6", "9", "between"]


class SnapshotEnvironment(TypedDict):
    brainc_available: bool
    tbrc_available: bool
    ollama_model: str | None


class SnapshotAttribution(TypedDict):
    lab: str
    tiekat_version: str
    hemavit: str


class SnapshotDeclaration(TypedDict):
    line_1: str
    line_2: str


class SnapshotIntegrity(TypedDict):
    content_hash: str | None
    annotation_hash: str | None


class SnapshotAnnotation(TypedDict):
    at: str
    note: str


class SovereignSnapshotDict(TypedDict, total=False):
    schema: str
    captured_at: str
    phios_version: str
    system: SnapshotSystem
    coherence: SnapshotCoherence
    sovereignty: SnapshotSovereignty
    session: SnapshotSession
    environment: SnapshotEnvironment
    operator_notes: str
    manifesto_link: str
    attribution: SnapshotAttribution
    declaration: SnapshotDeclaration
    integrity: SnapshotIntegrity
    annotations: list[SnapshotAnnotation]
    sha256: str


class SnapshotCompareResult(TypedDict, total=False):
    schema: str
    lt_delta: float
    trajectory_change: str
    time_between_s: int
    sovereignty_state_change: str
    error: str


@dataclass
class VerifyResult:
    ok: bool
    reason: str


def _canonical(data: dict[str, object]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rhythm_position(duration_s: int) -> Literal["3", "6", "9", "between"]:
    if duration_s % 9 == 0:
        return "9"
    if duration_s % 6 == 0:
        return "6"
    if duration_s % 3 == 0:
        return "3"
    return "between"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_safe_path(user_path: str, *, base_dir: Path | None = None) -> Path:
    """Resolve and validate a snapshot path for sovereign operations."""
    base = (base_dir or Path.cwd()).expanduser().resolve()
    raw = Path(user_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    resolved = (base / raw).resolve()
    if _is_within(resolved, base):
        return resolved
    raise ValueError("Relative path traversal outside cwd is not allowed")


class SovereignSnapshot:
    """Capture, verify, compare and annotate sovereign snapshots."""

    schema = "phios.v0.2.sovereign_snapshot"

    def capture(self, lt_result: LtResultDict, session: dict[str, object], operator_notes: str = "") -> SovereignSnapshotDict:
        now = datetime.now(timezone.utc).isoformat()
        hostname_hash = _sha256(socket.gethostname())[:12]
        components = lt_result["components"]
        history_raw = cast(list[float], session.get("history", []))
        history = [float(v) for v in history_raw][-9:]
        duration_s = int(session.get("duration_s", 0))

        snapshot: SovereignSnapshotDict = {
            "schema": self.schema,
            "captured_at": now,
            "phios_version": "v0.2",
            "system": {
                "hostname": hostname_hash,
                "os": platform.platform(),
                "python": platform.python_version(),
                "cpu_count": os.cpu_count(),
            },
            "coherence": {
                "lt_score": float(lt_result["lt"]),
                "a_on": float(components["A_stability"]),
                "psi_b": 1.0 - float(components["G_load"]),
                "g_score": float(components["G_load"]),
                "c_score": float(components["C_variance"]),
                "trajectory": str(session.get("trajectory", "stable")),
                "history": history,
            },
            "sovereignty": {
                "mode_active": True,
                "external_connections_blocked": True,
            },
            "session": {
                "duration_s": duration_s,
                "commands_run": int(session.get("commands_run", 0)),
                "resonance_moments_hit": int(session.get("resonance_moments_hit", 0)),
                "rhythm_position": _rhythm_position(duration_s),
            },
            "environment": {
                "brainc_available": ollama_available(),
                "tbrc_available": TBRCBridge().is_available(),
                "ollama_model": None,
            },
            "operator_notes": operator_notes,
            "manifesto_link": MANIFESTO_LINK,
            "attribution": {
                "lab": "PHI369 Labs / Parallax",
                "tiekat_version": "v8.1",
                "hemavit": "Structured coherence by consent and local agency.",
            },
            "declaration": {
                "line_1": "Sovereign. Coherent. Local. Free.",
                "line_2": "No " + "tele" + "metry. No cloud. No compromise.",
            },
        }

        content_for_hash = cast(dict[str, object], dict(snapshot))
        content_for_hash.pop("integrity", None)
        content_hash = _sha256(_canonical(content_for_hash) + operator_notes)
        snapshot["integrity"] = {"content_hash": content_hash, "annotation_hash": None}
        return snapshot

    def verify(self, snapshot_path: str) -> VerifyResult:
        try:
            safe_path = resolve_safe_path(snapshot_path)
            data = cast(SovereignSnapshotDict, json.loads(safe_path.read_text(encoding="utf-8")))
            integrity = data.get("integrity", {})
            given = integrity.get("content_hash") if isinstance(integrity, dict) else None
            if not given:
                return VerifyResult(False, "Missing integrity.content_hash")
            cloned = cast(dict[str, object], dict(data))
            cloned.pop("annotations", None)
            cloned.pop("integrity", None)
            operator_notes = str(data.get("operator_notes", ""))
            expected = _sha256(_canonical(cloned) + operator_notes)
            if given == expected:
                return VerifyResult(True, "content hash valid")
            return VerifyResult(False, "content hash mismatch")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            return VerifyResult(False, f"verify error: {exc}")

    def compare(self, snapshot_a: str, snapshot_b: str) -> SnapshotCompareResult:
        try:
            path_a = resolve_safe_path(snapshot_a)
            path_b = resolve_safe_path(snapshot_b)
            a = cast(SovereignSnapshotDict, json.loads(path_a.read_text(encoding="utf-8")))
            b = cast(SovereignSnapshotDict, json.loads(path_b.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            return {"schema": "phios.v0.2.snapshot_compare", "error": str(exc)}

        def _parse_ts(raw: str) -> datetime:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))

        coherence_a = cast(dict[str, object], a.get("coherence", {}))
        coherence_b = cast(dict[str, object], b.get("coherence", {}))
        sovereignty_a = cast(dict[str, object], a.get("sovereignty", {}))
        sovereignty_b = cast(dict[str, object], b.get("sovereignty", {}))

        lt_a = float(coherence_a.get("lt_score", 0.0))
        lt_b = float(coherence_b.get("lt_score", 0.0))
        t_a = str(coherence_a.get("trajectory", "unknown"))
        t_b = str(coherence_b.get("trajectory", "unknown"))
        s_a = bool(sovereignty_a.get("mode_active", False))
        s_b = bool(sovereignty_b.get("mode_active", False))

        delta_seconds = 0
        try:
            captured_a = str(a.get("captured_at", ""))
            captured_b = str(b.get("captured_at", ""))
            delta_seconds = int(abs((_parse_ts(captured_b) - _parse_ts(captured_a)).total_seconds()))
        except ValueError:
            delta_seconds = 0

        return {
            "schema": "phios.v0.2.snapshot_compare",
            "lt_delta": round(lt_b - lt_a, 6),
            "trajectory_change": f"{t_a} -> {t_b}",
            "time_between_s": delta_seconds,
            "sovereignty_state_change": f"{s_a} -> {s_b}",
        }

    def annotate(self, snapshot_path: str, annotation: str) -> None:
        path = resolve_safe_path(snapshot_path)
        data = cast(SovereignSnapshotDict, json.loads(path.read_text(encoding="utf-8")))
        notes = data.get("annotations", [])
        if not isinstance(notes, list):
            notes = []
        notes.append({"at": datetime.now(timezone.utc).isoformat(), "note": annotation})
        data["annotations"] = cast(list[SnapshotAnnotation], notes)
        integrity = data.get("integrity", {"content_hash": None, "annotation_hash": None})
        existing_hash = integrity.get("content_hash") if isinstance(integrity, dict) else None
        data["integrity"] = {
            "content_hash": existing_hash,
            "annotation_hash": _sha256(_canonical({"annotations": notes})),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def export_snapshot(path: str) -> Path:
    from phios.core.lt_engine import compute_lt

    session: dict[str, object] = {
        "history": [compute_lt().get("lt", 0.5)],
        "duration_s": 0,
        "commands_run": 0,
        "resonance_moments_hit": 0,
        "trajectory": "stable",
    }
    snap = SovereignSnapshot().capture(compute_lt(), session)
    legacy = dict(snap)
    legacy.pop("sha256", None)
    legacy_hash = _sha256(_canonical(cast(dict[str, object], legacy)))
    snap["sha256"] = legacy_hash
    out_path = resolve_safe_path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return out_path


def verify_snapshot(path: str) -> tuple[bool, str]:
    try:
        safe_path = resolve_safe_path(path)
        data = cast(SovereignSnapshotDict, json.loads(safe_path.read_text(encoding="utf-8")))
        if "sha256" in data:
            given = data.pop("sha256")
            expected = _sha256(_canonical(cast(dict[str, object], data)))
            return (given == expected, "Hash matches" if given == expected else "Hash mismatch")
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        return False, f"Unable to read export: {exc}"

    result = SovereignSnapshot().verify(path)
    return result.ok, result.reason
