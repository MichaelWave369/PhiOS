"""Local Visual Bloom adapter for PhiOS.

This module reads live PhiKernel field_state and renders local bloom artifacts.
It is a local-first adapter layer: PhiKernel remains runtime source-of-truth.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
import importlib.resources as resources

VALID_PRESETS = {"stable", "ritual", "diagnostic", "bloom"}
VALID_LENSES = {"stable", "ritual", "diagnostic", "bloom"}


class VisualizerError(RuntimeError):
    """Raised when visualizer field_state, journaling, or rendering fails."""


def run_phik_json(args: list[str]) -> dict[str, object]:
    """Run a phik command with --json and return parsed JSON object."""
    if shutil.which("phik") is None:
        raise VisualizerError("PhiKernel CLI `phik` is unavailable. Install/initialize PhiKernel first.")

    cmd = ["phik", *args, "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=False)
    except OSError as exc:
        raise VisualizerError(f"Failed to execute {' '.join(cmd)}: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit code {proc.returncode}"
        raise VisualizerError(f"PhiKernel command failed ({' '.join(cmd)}): {detail}")

    raw = (proc.stdout or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VisualizerError(f"Invalid JSON from {' '.join(cmd)}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise VisualizerError("PhiKernel JSON payload must be an object.")
    return payload


def _to_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _seed_from_identity(status_data: dict[str, object]) -> int:
    for key in ("anchor_id", "sovereign_id", "identity", "anchor", "heart_state"):
        value = status_data.get(key)
        if value is None:
            continue
        token = str(value)
        if token:
            return abs(hash(token)) % 1_000_000 + 369
    return 369369


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _journal_root(journal_dir: Path | None = None) -> Path:
    return journal_dir.expanduser() if journal_dir else (Path.home() / ".phios" / "journal" / "visual_bloom")


def _short_session_id(session_id: str) -> str:
    return session_id[:12]


def _sanitize_collection(name: str) -> str:
    safe = "".join(ch.lower() if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in name.strip())
    safe = "-".join(part for part in safe.split("-") if part)
    if not safe:
        raise VisualizerError("Collection name is empty after sanitization.")
    return safe


def poll_kernel_state() -> tuple[dict[str, object], dict[str, object]]:
    """Fetch current PhiKernel field and status state."""
    return run_phik_json(["field"]), run_phik_json(["status"])


def map_kernel_to_visual_params(field_data: dict[str, object], status_data: dict[str, object]) -> dict[str, object]:
    """Map kernel field_state into stable visual parameter space."""
    coherence = _to_float(field_data.get("C_current", field_data.get("coherence", 0.809)), 0.809)
    coherence = _clamp(coherence, 0.0, 1.0)

    frequency = _to_float(field_data.get("phi_flow", field_data.get("resonance_hz", 7.83)), 7.83)
    frequency = _clamp(frequency * 12.0 if frequency <= 3.0 else frequency, 1.0, 40.0)

    drift_band = str(field_data.get("field_band", field_data.get("drift_band", "Watch")))
    drift_norm = drift_band.lower()
    if drift_norm.startswith("stable") or drift_norm.startswith("green"):
        particle_count = 900
    elif drift_norm.startswith("alert") or drift_norm.startswith("red"):
        particle_count = 2200
    else:
        particle_count = 1500

    grace = _to_float(field_data.get("grace", field_data.get("coherence_percent", coherence * 100.0)), coherence * 100.0)
    grace_norm = _clamp(grace / 100.0, 0.0, 1.0)
    noise_scale = _clamp(0.002 + (1.0 - coherence) * 0.008, 0.002, 0.01)

    return {
        "seed": _seed_from_identity(status_data),
        "coherenceC": round(coherence, 4),
        "goldenInf": 1.618,
        "frequency": round(frequency, 3),
        "particleCount": int(particle_count),
        "noiseScale": round(noise_scale, 6),
        "driftBand": drift_band,
        "grace": round(grace_norm, 4),
        "sourceLabel": "PhiOS Visual Bloom · PhiKernel field_state",
    }


def apply_visual_preset(params: dict[str, object], preset_name: str | None) -> dict[str, object]:
    preset = (preset_name or "").strip().lower() or None
    if preset is not None and preset not in VALID_PRESETS:
        raise VisualizerError(f"Unknown preset '{preset_name}'. Valid presets: {', '.join(sorted(VALID_PRESETS))}")

    out = dict(params)
    out["preset"] = preset or "none"
    out["trailStrength"] = _clamp(_to_float(out.get("trailStrength"), 1.0), 0.5, 2.0)
    out["glowGain"] = _clamp(_to_float(out.get("glowGain"), 1.0), 0.5, 2.0)
    out["speedBias"] = _clamp(_to_float(out.get("speedBias"), 1.0), 0.5, 2.0)
    out["turbulenceBias"] = _clamp(_to_float(out.get("turbulenceBias"), 1.0), 0.5, 2.0)
    if preset is None:
        return out

    bias = {
        "stable": (0.9, 0.9, 0.92, 0.8),
        "ritual": (1.1, 1.1, 0.95, 0.9),
        "diagnostic": (0.95, 1.0, 1.0, 1.15),
        "bloom": (1.2, 1.25, 1.12, 1.05),
    }[preset]
    out["trailStrength"] = _clamp(out["trailStrength"] * bias[0], 0.5, 2.0)
    out["glowGain"] = _clamp(out["glowGain"] * bias[1], 0.5, 2.0)
    out["speedBias"] = _clamp(out["speedBias"] * bias[2], 0.5, 2.0)
    out["turbulenceBias"] = _clamp(out["turbulenceBias"] * bias[3], 0.5, 2.0)
    return out


def apply_visual_lens(params: dict[str, object], lens_name: str | None) -> dict[str, object]:
    lens = (lens_name or "").strip().lower() or None
    if lens is not None and lens not in VALID_LENSES:
        raise VisualizerError(f"Unknown lens '{lens_name}'. Valid lenses: {', '.join(sorted(VALID_LENSES))}")

    out = dict(params)
    out["lens"] = lens or "none"
    out["paletteShift"] = _clamp(_to_float(out.get("paletteShift"), 1.0), 0.8, 1.3)
    out["damping"] = _clamp(_to_float(out.get("damping"), 1.0), 0.7, 1.4)
    if lens is None:
        return out

    bias = {
        "stable": (0.92, 1.12),
        "ritual": (1.05, 0.96),
        "diagnostic": (0.88, 1.22),
        "bloom": (1.18, 0.9),
    }[lens]
    out["paletteShift"] = _clamp(out["paletteShift"] * bias[0], 0.8, 1.3)
    out["damping"] = _clamp(out["damping"] * bias[1], 0.7, 1.4)
    return out


def apply_audio_reactive_modulation(params: dict[str, object], enabled: bool) -> tuple[dict[str, object], str]:
    out = dict(params)
    if not enabled:
        out["audioReactive"] = False
        out["audioStatus"] = "off"
        out["audioGain"] = 1.0
        return out, "off"

    try:
        import sounddevice  # type: ignore  # pragma: no cover

        _ = sounddevice.default.device  # pragma: no cover
        out["audioReactive"] = True
        out["audioStatus"] = "enabled"
        out["audioGain"] = 1.1
        out["turbulenceBias"] = _clamp(_to_float(out.get("turbulenceBias"), 1.0) * 1.08, 0.5, 2.0)
        out["glowGain"] = _clamp(_to_float(out.get("glowGain"), 1.0) * 1.1, 0.5, 2.0)
        return out, "enabled"
    except Exception:
        out["audioReactive"] = False
        out["audioStatus"] = "unavailable"
        out["audioGain"] = 1.0
        return out, "unavailable"


def _with_live_contract(
    params: dict[str, object],
    *,
    mode: str,
    refresh_seconds: float | None = None,
    session_id: str | None = None,
    session_label: str | None = None,
    state_timestamp: str | None = None,
    preset: str | None = None,
    lens: str | None = None,
    audio_requested: bool = False,
    collection: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        **params,
        "mode": mode,
        "timestamp": int(time.time()),
        "preset": preset or params.get("preset", "none"),
        "lens": lens or params.get("lens", "none"),
        "audioRequested": bool(audio_requested),
    }
    if refresh_seconds is not None:
        payload["refreshSeconds"] = round(max(refresh_seconds, 0.2), 2)
    if session_id:
        payload["sessionId"] = session_id
        payload["sessionIdShort"] = _short_session_id(session_id)
    if session_label:
        payload["sessionLabel"] = session_label
    if state_timestamp:
        payload["stateTimestamp"] = state_timestamp
    if collection:
        payload["collection"] = collection
    return payload


def create_visual_bloom_session(
    *,
    mode: str,
    params: dict[str, object],
    refresh_seconds: float | None,
    output_path: Path,
    journal_dir: Path | None = None,
    label: str | None = None,
    source_command: str = "phi view --mode sonic",
    collection: str | None = None,
) -> Path:
    root = _journal_root(journal_dir)
    created_at = _iso_now()
    session_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{int(time.time_ns() % 1_000_000):06d}"
    session_dir = root / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    latest_params = session_dir / "latest.params.json"
    session_json = session_dir / "session.json"

    session_doc: dict[str, object] = {
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": created_at,
        "mode": mode,
        "label": label,
        "collection": collection,
        "seed": params.get("seed"),
        "refreshSeconds": refresh_seconds,
        "driftBand": params.get("driftBand"),
        "preset": params.get("preset", "none"),
        "lens": params.get("lens", "none"),
        "audioReactive": bool(params.get("audioReactive", False)),
        "source_command": source_command,
        "artifact_paths": {"html": str(output_path), "latest_params": str(latest_params)},
        "core_params": {
            "seed": params.get("seed"),
            "coherenceC": params.get("coherenceC"),
            "goldenInf": params.get("goldenInf"),
            "frequency": params.get("frequency"),
            "particleCount": params.get("particleCount"),
            "noiseScale": params.get("noiseScale"),
            "driftBand": params.get("driftBand"),
            "preset": params.get("preset", "none"),
            "lens": params.get("lens", "none"),
            "audioReactive": bool(params.get("audioReactive", False)),
        },
        "states": [],
    }
    session_json.write_text(json.dumps(session_doc, indent=2), encoding="utf-8")
    return session_dir


def load_visual_bloom_session(session_ref: str, journal_dir: Path | None = None) -> dict[str, object]:
    ref = Path(session_ref).expanduser()
    session_json = ref if ref.suffix == ".json" else (_journal_root(journal_dir) / session_ref / "session.json")
    if not session_json.exists():
        raise VisualizerError(f"Replay session file not found: {session_json}")
    try:
        data = json.loads(session_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualizerError(f"Replay session JSON is invalid: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise VisualizerError("Replay session document must be an object.")
    return data


def list_visual_bloom_sessions(*, journal_dir: Path | None = None, collection: str | None = None) -> list[dict[str, object]]:
    root = _journal_root(journal_dir)
    if not root.exists():
        return []
    wanted = _sanitize_collection(collection) if collection else None
    out: list[dict[str, object]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        session_json = entry / "session.json"
        if not session_json.exists():
            continue
        try:
            doc = json.loads(session_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        coll = doc.get("collection")
        if wanted and coll != wanted:
            continue
        states = doc.get("states") if isinstance(doc.get("states"), list) else []
        latest = states[-1] if states else {}
        latest_ts = latest.get("stateTimestamp") if isinstance(latest, dict) else None
        out.append(
            {
                "session_id": doc.get("session_id", entry.name),
                "created_at": doc.get("created_at", "unknown"),
                "updated_at": doc.get("updated_at", "unknown"),
                "label": doc.get("label") or "",
                "collection": doc.get("collection") or "",
                "mode": doc.get("mode", "unknown"),
                "preset": doc.get("preset", "none"),
                "lens": doc.get("lens", "none"),
                "audio": "on" if doc.get("audioReactive", False) else "off",
                "latest_timestamp": latest_ts or "",
            }
        )
    out.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return out


def list_visual_bloom_collections(*, journal_dir: Path | None = None) -> list[str]:
    sessions = list_visual_bloom_sessions(journal_dir=journal_dir)
    cols = {str(s.get("collection", "")).strip() for s in sessions if str(s.get("collection", "")).strip()}
    return sorted(cols)


def resolve_visual_bloom_state_ref(ref: str, *, journal_dir: Path | None = None) -> tuple[dict[str, object], dict[str, object], int]:
    session_ref = ref
    state_index: int | None = None
    if ":" in ref:
        left, right = ref.rsplit(":", 1)
        if right.lstrip("-").isdigit():
            session_ref = left
            state_index = int(right)

    session = load_visual_bloom_session(session_ref, journal_dir=journal_dir)
    states = session.get("states")
    if not isinstance(states, list) or not states:
        raise VisualizerError(f"Session has no recorded states: {session_ref}")

    idx = len(states) - 1 if state_index is None else state_index
    if idx < 0:
        idx = len(states) + idx
    if idx < 0 or idx >= len(states):
        raise VisualizerError(f"State index out of range for {session_ref}: {state_index}")

    state = states[idx]
    if not isinstance(state, dict):
        raise VisualizerError(f"Malformed state record in {session_ref} at index {idx}")
    return session, state, idx


def load_visual_bloom_state(ref: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    session, state, idx = resolve_visual_bloom_state_ref(ref, journal_dir=journal_dir)
    merged = dict(state)
    merged.setdefault("sessionId", str(session.get("session_id", "replay")))
    merged.setdefault("sessionLabel", str(session.get("label", "")))
    merged.setdefault("collection", str(session.get("collection", "")))
    merged.setdefault("preset", str(session.get("preset", "none")))
    merged.setdefault("lens", str(session.get("lens", "none")))
    merged.setdefault("stateIndex", idx)
    return merged


def append_or_update_journal_state(*, session_dir: Path, params: dict[str, object], output_html: Path) -> Path:
    session_json = session_dir / "session.json"
    latest_params = session_dir / "latest.params.json"
    try:
        doc = json.loads(session_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualizerError(f"Session metadata is invalid JSON: {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise VisualizerError("Session metadata must be an object.")

    state_record = {
        "timestamp": params.get("timestamp", int(time.time())),
        "stateTimestamp": params.get("stateTimestamp", _iso_now()),
        "seed": params.get("seed"),
        "coherenceC": params.get("coherenceC"),
        "goldenInf": params.get("goldenInf"),
        "frequency": params.get("frequency"),
        "particleCount": params.get("particleCount"),
        "noiseScale": params.get("noiseScale"),
        "mode": params.get("mode"),
        "driftBand": params.get("driftBand"),
        "refreshSeconds": params.get("refreshSeconds"),
        "grace": params.get("grace"),
        "preset": params.get("preset", "none"),
        "lens": params.get("lens", "none"),
        "audioReactive": bool(params.get("audioReactive", False)),
        "audioStatus": params.get("audioStatus", "off"),
        "trailStrength": params.get("trailStrength"),
        "glowGain": params.get("glowGain"),
        "speedBias": params.get("speedBias"),
        "turbulenceBias": params.get("turbulenceBias"),
        "paletteShift": params.get("paletteShift"),
        "damping": params.get("damping"),
        "collection": params.get("collection", doc.get("collection", "")),
    }
    states = doc.get("states")
    if not isinstance(states, list):
        states = []
    states.append(state_record)
    doc["states"] = states
    doc["seed"] = params.get("seed")
    doc["driftBand"] = params.get("driftBand")
    doc["preset"] = params.get("preset", doc.get("preset", "none"))
    doc["lens"] = params.get("lens", doc.get("lens", "none"))
    doc["audioReactive"] = bool(params.get("audioReactive", doc.get("audioReactive", False)))
    if params.get("collection"):
        doc["collection"] = params.get("collection")
    doc["core_params"] = {
        "seed": params.get("seed"),
        "coherenceC": params.get("coherenceC"),
        "goldenInf": params.get("goldenInf"),
        "frequency": params.get("frequency"),
        "particleCount": params.get("particleCount"),
        "noiseScale": params.get("noiseScale"),
        "driftBand": params.get("driftBand"),
        "preset": params.get("preset", "none"),
        "lens": params.get("lens", "none"),
        "audioReactive": bool(params.get("audioReactive", False)),
        "collection": params.get("collection", doc.get("collection", "")),
    }
    doc["artifact_paths"] = {"html": str(output_html), "latest_params": str(latest_params)}
    doc["updated_at"] = _iso_now()
    session_json.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    latest_params.write_text(json.dumps(params, indent=2), encoding="utf-8")
    return latest_params


def render_bloom_html(params: dict[str, object], *, live_mode: bool = False, refresh_seconds: float = 2.0, params_path: str = "") -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_emergence.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load visual template: {exc}") from exc
    marker = "__PHIOS_INITIAL_PARAMS_JSON__"
    if marker not in template:
        raise VisualizerError("Template marker __PHIOS_INITIAL_PARAMS_JSON__ not found.")
    html = template.replace(marker, json.dumps(params, separators=(",", ":")))
    html = html.replace("__PHIOS_LIVE_ENABLED__", "true" if live_mode else "false")
    html = html.replace("__PHIOS_REFRESH_MS__", str(int(max(refresh_seconds, 0.2) * 1000)))
    html = html.replace("__PHIOS_REFRESH_SECONDS__", f"{max(refresh_seconds, 0.2):.2f}")
    html = html.replace("__PHIOS_PARAMS_PATH__", params_path)
    return html


def render_compare_bloom_html(left_params: dict[str, object], right_params: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_compare.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load compare template: {exc}") from exc

    left_html = render_bloom_html(left_params, live_mode=False)
    right_html = render_bloom_html(right_params, live_mode=False)
    left_b64 = base64.b64encode(left_html.encode("utf-8")).decode("ascii")
    right_b64 = base64.b64encode(right_html.encode("utf-8")).decode("ascii")

    html = template.replace("__PHIOS_COMPARE_ENABLED__", "true")
    html = html.replace("__PHIOS_COMPARE_LEFT_JSON__", json.dumps(left_params, separators=(",", ":")))
    html = html.replace("__PHIOS_COMPARE_RIGHT_JSON__", json.dumps(right_params, separators=(",", ":")))
    html = html.replace("__PHIOS_COMPARE_LEFT_B64__", left_b64)
    html = html.replace("__PHIOS_COMPARE_RIGHT_B64__", right_b64)
    return html


def write_bloom_file(html: str, output_path: Path) -> Path:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
    except OSError:
        tmp = tempfile.NamedTemporaryFile(prefix="phios_bloom_", suffix=".html", delete=False)
        path = Path(tmp.name)
        tmp.write(html.encode("utf-8"))
        tmp.close()
        return path


def write_live_params_json(params: dict[str, object], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(params, indent=2), encoding="utf-8")
    return output_path


def _open_browser(path: Path, open_browser: bool) -> None:
    if not open_browser:
        return
    try:
        webbrowser.open(path.as_uri())
    except Exception as exc:  # pragma: no cover
        print(f"Warning: bloom written but browser launch failed: {exc}")


def _compose_visual_params(mapped: dict[str, object], *, preset: str | None, lens: str | None, audio_reactive: bool) -> dict[str, object]:
    params = apply_visual_preset(mapped, preset)
    params = apply_visual_lens(params, lens)
    params, audio_state = apply_audio_reactive_modulation(params, audio_reactive)
    if audio_reactive and audio_state == "unavailable":
        print("Warning: audio-reactive requested but unavailable; continuing without audio modulation.")
    return params


def launch_bloom(
    output_path: Path | None = None,
    open_browser: bool = True,
    *,
    journal: bool = False,
    journal_dir: Path | None = None,
    label: str | None = None,
    source_command: str = "phi view --mode sonic",
    preset: str | None = None,
    lens: str | None = None,
    audio_reactive: bool = False,
    collection: str | None = None,
) -> Path:
    field_data, status_data = poll_kernel_state()
    mapped = map_kernel_to_visual_params(field_data, status_data)
    mapped = _compose_visual_params(mapped, preset=preset, lens=lens, audio_reactive=audio_reactive)
    target = output_path or Path("/tmp/phios_bloom.html")
    session_dir: Path | None = None
    session_id: str | None = None
    safe_collection = _sanitize_collection(collection) if collection else None
    if journal:
        session_dir = create_visual_bloom_session(
            mode="snapshot",
            params=mapped,
            refresh_seconds=None,
            output_path=target,
            journal_dir=journal_dir,
            label=label,
            source_command=source_command,
            collection=safe_collection,
        )
        session_id = session_dir.name
    params = _with_live_contract(
        mapped,
        mode="snapshot",
        session_id=session_id,
        session_label=label,
        state_timestamp=_iso_now(),
        preset=preset,
        lens=lens,
        audio_requested=audio_reactive,
        collection=safe_collection,
    )
    written = write_bloom_file(render_bloom_html(params, live_mode=False), target)
    if session_dir is not None:
        append_or_update_journal_state(session_dir=session_dir, params=params, output_html=written)
    _open_browser(written, open_browser)
    return written


def launch_live_bloom(
    output_path: Path | None = None,
    *,
    refresh_seconds: float = 2.0,
    duration: float | None = None,
    open_browser: bool = True,
    journal: bool = False,
    journal_dir: Path | None = None,
    label: str | None = None,
    source_command: str = "phi view --mode sonic --live",
    preset: str | None = None,
    lens: str | None = None,
    audio_reactive: bool = False,
    collection: str | None = None,
) -> Path:
    interval = max(refresh_seconds, 0.2)
    target = output_path or Path("/tmp/phios_bloom.html")
    params_path = target.with_suffix(".params.json")
    written = target
    safe_collection = _sanitize_collection(collection) if collection else None
    try:
        field_data, status_data = poll_kernel_state()
        mapped = _compose_visual_params(map_kernel_to_visual_params(field_data, status_data), preset=preset, lens=lens, audio_reactive=audio_reactive)
        session_dir: Path | None = None
        session_id: str | None = None
        if journal:
            session_dir = create_visual_bloom_session(
                mode="live",
                params=mapped,
                refresh_seconds=interval,
                output_path=target,
                journal_dir=journal_dir,
                label=label,
                source_command=source_command,
                collection=safe_collection,
            )
            session_id = session_dir.name
        first_params = _with_live_contract(
            mapped,
            mode="live",
            refresh_seconds=interval,
            session_id=session_id,
            session_label=label,
            state_timestamp=_iso_now(),
            preset=preset,
            lens=lens,
            audio_requested=audio_reactive,
            collection=safe_collection,
        )
        write_live_params_json(first_params, params_path)
        written = write_bloom_file(render_bloom_html(first_params, live_mode=True, refresh_seconds=interval, params_path=params_path.name), target)
        if session_dir is not None:
            append_or_update_journal_state(session_dir=session_dir, params=first_params, output_html=written)
        _open_browser(written, open_browser)
        start = time.monotonic()
        while True:
            if duration is not None and (time.monotonic() - start) >= duration:
                return written
            time.sleep(interval)
            field_data, status_data = poll_kernel_state()
            mapped = _compose_visual_params(map_kernel_to_visual_params(field_data, status_data), preset=preset, lens=lens, audio_reactive=audio_reactive)
            params = _with_live_contract(
                mapped,
                mode="live",
                refresh_seconds=interval,
                session_id=session_id,
                session_label=label,
                state_timestamp=_iso_now(),
                preset=preset,
                lens=lens,
                audio_requested=audio_reactive,
                collection=safe_collection,
            )
            write_live_params_json(params, params_path)
            if session_dir is not None:
                append_or_update_journal_state(session_dir=session_dir, params=params, output_html=written)
    except KeyboardInterrupt:
        return written


def launch_replay_bloom(
    session_ref: str,
    *,
    output_path: Path | None = None,
    open_browser: bool = True,
    journal_dir: Path | None = None,
    preset: str | None = None,
    lens: str | None = None,
    audio_reactive: bool = False,
) -> Path:
    session, last_state, _ = resolve_visual_bloom_state_ref(session_ref, journal_dir=journal_dir)

    effective_preset = preset or str(last_state.get("preset", session.get("preset", "none")))
    effective_lens = lens or str(last_state.get("lens", session.get("lens", "none")))
    if effective_preset == "none":
        effective_preset = None
    if effective_lens == "none":
        effective_lens = None

    replay_base = _compose_visual_params(dict(last_state), preset=effective_preset, lens=effective_lens, audio_reactive=audio_reactive)
    params = _with_live_contract(
        replay_base,
        mode="replay",
        session_id=str(session.get("session_id", "replay")),
        session_label=str(session.get("label", "")) or None,
        state_timestamp=str(last_state.get("stateTimestamp", _iso_now())),
        preset=effective_preset,
        lens=effective_lens,
        audio_requested=audio_reactive,
        collection=str(session.get("collection", "")) or None,
    )
    params["sourceLabel"] = "PhiOS Visual Bloom · Replay"
    target = output_path or Path("/tmp/phios_bloom_replay.html")
    written = write_bloom_file(render_bloom_html(params, live_mode=False), target)
    _open_browser(written, open_browser)
    return written


def launch_compare_bloom(
    left_ref: str,
    right_ref: str,
    *,
    output_path: Path | None = None,
    open_browser: bool = True,
    journal_dir: Path | None = None,
) -> Path:
    left_session, left_state, _ = resolve_visual_bloom_state_ref(left_ref, journal_dir=journal_dir)
    right_session, right_state, _ = resolve_visual_bloom_state_ref(right_ref, journal_dir=journal_dir)

    left_params = _with_live_contract(
        dict(left_state),
        mode="compare-left",
        session_id=str(left_session.get("session_id", "left")),
        session_label=str(left_session.get("label", "")) or None,
        state_timestamp=str(left_state.get("stateTimestamp", _iso_now())),
        preset=str(left_state.get("preset", left_session.get("preset", "none"))),
        lens=str(left_state.get("lens", left_session.get("lens", "none"))),
        collection=str(left_session.get("collection", "")) or None,
    )
    left_params["sourceLabel"] = "PhiOS Visual Bloom · Compare Left"

    right_params = _with_live_contract(
        dict(right_state),
        mode="compare-right",
        session_id=str(right_session.get("session_id", "right")),
        session_label=str(right_session.get("label", "")) or None,
        state_timestamp=str(right_state.get("stateTimestamp", _iso_now())),
        preset=str(right_state.get("preset", right_session.get("preset", "none"))),
        lens=str(right_state.get("lens", right_session.get("lens", "none"))),
        collection=str(right_session.get("collection", "")) or None,
    )
    right_params["sourceLabel"] = "PhiOS Visual Bloom · Compare Right"

    html = render_compare_bloom_html(left_params, right_params)
    target = output_path or Path("/tmp/phios_bloom_compare.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written
