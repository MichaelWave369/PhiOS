"""Sovereign export/verify utilities."""

from __future__ import annotations

import hashlib
import json
import platform
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.core.brainc_client import ollama_available
from phios.core.tbrc_bridge import TBRCBridge


MANIFESTO_LINK = "https://enterthefield.org/phios"


@dataclass
class VerifyResult:
    ok: bool
    reason: str


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rhythm_position(duration_s: int) -> str:
    if duration_s % 9 == 0:
        return "9"
    if duration_s % 6 == 0:
        return "6"
    if duration_s % 3 == 0:
        return "3"
    return "between"


class SovereignSnapshot:
    schema = "phios.v0.2.sovereign_snapshot"

    def capture(self, lt_result: dict[str, Any], session: dict[str, Any], operator_notes: str = "") -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        hostname_hash = _sha256(socket.gethostname())[:12]
        components = lt_result.get("components", {}) if isinstance(lt_result, dict) else {}
        history = list(session.get("history", []))[-9:]
        duration_s = int(session.get("duration_s", 0))

        snapshot: dict[str, Any] = {
            "schema": self.schema,
            "captured_at": now,
            "phios_version": "v0.2",
            "system": {
                "hostname": hostname_hash,
                "os": platform.platform(),
                "python": platform.python_version(),
                "cpu_count": __import__("os").cpu_count(),
            },
            "coherence": {
                "lt_score": float(lt_result.get("lt", 0.5)),
                "a_on": float(components.get("A_stability", 0.5)),
                "psi_b": 1.0 - float(components.get("G_load", 0.5)),
                "g_score": float(components.get("G_load", 0.5)),
                "c_score": float(components.get("C_variance", 0.5)),
                "trajectory": str(session.get("trajectory", "stable")),
                "history": [float(x) for x in history],
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

        content_for_hash = dict(snapshot)
        content_for_hash.pop("integrity", None)
        content_hash = _sha256(_canonical(content_for_hash) + operator_notes)
        snapshot["integrity"] = {"content_hash": content_hash, "annotation_hash": None}
        return snapshot

    def verify(self, snapshot_path: str) -> VerifyResult:
        try:
            data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
            integrity = data.get("integrity", {})
            given = integrity.get("content_hash")
            if not given:
                return VerifyResult(False, "Missing integrity.content_hash")
            cloned = dict(data)
            cloned.pop("annotations", None)
            cloned.pop("integrity", None)
            operator_notes = str(data.get("operator_notes", ""))
            expected = _sha256(_canonical(cloned) + operator_notes)
            if given == expected:
                return VerifyResult(True, "content hash valid")
            return VerifyResult(False, "content hash mismatch")
        except Exception as exc:
            return VerifyResult(False, f"verify error: {exc}")

    def compare(self, snapshot_a: str, snapshot_b: str) -> dict[str, Any]:
        try:
            a = json.loads(Path(snapshot_a).read_text(encoding="utf-8"))
            b = json.loads(Path(snapshot_b).read_text(encoding="utf-8"))
        except Exception as exc:
            return {"schema": "phios.v0.2.snapshot_compare", "error": str(exc)}

        def _parse_ts(raw: str) -> datetime:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))

        lt_a = float(a.get("coherence", {}).get("lt_score", 0.0))
        lt_b = float(b.get("coherence", {}).get("lt_score", 0.0))
        t_a = str(a.get("coherence", {}).get("trajectory", "unknown"))
        t_b = str(b.get("coherence", {}).get("trajectory", "unknown"))
        s_a = bool(a.get("sovereignty", {}).get("mode_active", False))
        s_b = bool(b.get("sovereignty", {}).get("mode_active", False))

        delta_seconds = 0
        try:
            delta_seconds = int(abs((_parse_ts(str(b.get("captured_at"))) - _parse_ts(str(a.get("captured_at")))).total_seconds()))
        except Exception:
            delta_seconds = 0

        return {
            "schema": "phios.v0.2.snapshot_compare",
            "lt_delta": round(lt_b - lt_a, 6),
            "trajectory_change": f"{t_a} -> {t_b}",
            "time_between_s": delta_seconds,
            "sovereignty_state_change": f"{s_a} -> {s_b}",
        }

    def annotate(self, snapshot_path: str, annotation: str) -> None:
        path = Path(snapshot_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        notes = data.get("annotations", [])
        if not isinstance(notes, list):
            notes = []
        notes.append({"at": datetime.now(timezone.utc).isoformat(), "note": annotation})
        data["annotations"] = notes
        integrity = data.get("integrity", {})
        existing_hash = integrity.get("content_hash")
        integrity["content_hash"] = existing_hash
        integrity["annotation_hash"] = _sha256(_canonical({"annotations": notes}))
        data["integrity"] = integrity
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def export_snapshot(path: str) -> Path:
    from phios.core.lt_engine import compute_lt

    session = {"history": [compute_lt().get("lt", 0.5)], "duration_s": 0, "commands_run": 0, "resonance_moments_hit": 0, "trajectory": "stable"}
    snap = SovereignSnapshot().capture(compute_lt(), session)
    legacy = dict(snap)
    legacy.pop("sha256", None)
    legacy_hash = _sha256(_canonical(legacy))
    snap["sha256"] = legacy_hash
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return out_path


def verify_snapshot(path: str) -> tuple[bool, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if "sha256" in data:
            given = data.pop("sha256")
            expected = _sha256(_canonical(data))
            return (given == expected, "Hash matches" if given == expected else "Hash mismatch")
    except Exception as exc:
        return False, f"Unable to read export: {exc}"

    result = SovereignSnapshot().verify(path)
    return result.ok, result.reason
