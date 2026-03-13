"""Local Visual Bloom adapter for PhiOS.

This module reads live PhiKernel field_state and renders local bloom artifacts.
It is a local-first adapter layer: PhiKernel remains runtime source-of-truth.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
import importlib.resources as resources

from phios.core.constants import (
    BIO_MODEL_PROVENANCE,
    BIO_VACUUM_BAND_HIGH,
    BIO_VACUUM_BAND_LOW,
    BIO_VACUUM_STATUS,
    BIO_VACUUM_TARGET,
    C_STAR_THEORETICAL,
    C_STAR_THEORETICAL_TRIG_EQUIV,
    HUNTER_C_STATUS,
    PHI,
)
from phios.ml.golden_kernels import golden_angular_rbf, golden_rbf
from phios.core.sectors import (
    dominant_sector,
    infer_visual_bloom_sector_weights,
    list_visual_bloom_sectors,
)
from phios.ml.golden_lattice import adaptive_golden_affinity, golden_lattice_kernel_l1
from phios.ml.benchmark_recommendations import benchmark_recommendation_strategies
from phios.ml.golden_atlas import (
    build_golden_atlas_graph,
    build_golden_atlas_summary,
    build_lattice_4d_nodes,
    compute_atlas_heat,
    find_path_to_bio_band,
    find_path_to_target,
    nearest_lattice_node,
)

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


def normalize_visual_bloom_tags(tags: str | list[str] | None) -> list[str]:
    if tags is None:
        return []
    raw = tags.split(",") if isinstance(tags, str) else tags
    out: list[str] = []
    for item in raw:
        token = str(item).strip()
        if not token:
            continue
        safe = _sanitize_collection(token)
        if safe not in out:
            out.append(safe)
    return out


def augment_visual_bloom_preview_metadata(
    *,
    source: str,
    preview_path: Path | None = None,
    preview_type: str = "metadata-placeholder",
    status: str = "placeholder",
) -> dict[str, object]:
    """Build deterministic preview metadata for sessions/bundles.

    This phase stores metadata-first preview contracts so future image capture can
    populate `preview_source` without changing schema.
    """
    return {
        "preview_type": preview_type,
        "preview_source": str(preview_path) if preview_path is not None else "",
        "preview_generated_at": _iso_now(),
        "preview_status": status,
        "preview_origin": source,
    }


def build_visual_bloom_bio_metadata(params: dict[str, object]) -> dict[str, object]:
    coherence = _to_float(params.get("coherenceC"), C_STAR_THEORETICAL)
    score = _clamp(1.0 - abs(coherence - BIO_VACUUM_TARGET) / 0.02, 0.0, 1.0)
    return {
        "bio_target": BIO_VACUUM_TARGET,
        "bio_band_low": BIO_VACUUM_BAND_LOW,
        "bio_band_high": BIO_VACUUM_BAND_HIGH,
        "bio_status": BIO_VACUUM_STATUS,
        "hunter_c_status": HUNTER_C_STATUS,
        "model_provenance": BIO_MODEL_PROVENANCE,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_score": round(score, 6),
        "bio_distance_from_target": round(abs(coherence - BIO_VACUUM_TARGET), 6),
    }


def attach_visual_bloom_bio_metadata(params: dict[str, object], *, include_proxy: bool = False) -> dict[str, object]:
    out = dict(params)
    bio = build_visual_bloom_bio_metadata(out)
    if include_proxy:
        for key in ("hrv_coherence", "eeg_gamma", "neural_spike_density", "atp_flux", "psi_bar_psi"):
            if key in out:
                bio[key] = out.get(key)
    out["bio"] = bio
    return out


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

    payload = {
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
    return attach_visual_bloom_bio_metadata(payload)


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
    out["trailStrength"] = _clamp(_to_float(out.get("trailStrength"), 1.0) * bias[0], 0.5, 2.0)
    out["glowGain"] = _clamp(_to_float(out.get("glowGain"), 1.0) * bias[1], 0.5, 2.0)
    out["speedBias"] = _clamp(_to_float(out.get("speedBias"), 1.0) * bias[2], 0.5, 2.0)
    out["turbulenceBias"] = _clamp(_to_float(out.get("turbulenceBias"), 1.0) * bias[3], 0.5, 2.0)
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
    out["paletteShift"] = _clamp(_to_float(out.get("paletteShift"), 1.0) * bias[0], 0.8, 1.3)
    out["damping"] = _clamp(_to_float(out.get("damping"), 1.0) * bias[1], 0.7, 1.4)
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
    tags: str | list[str] | None = None,
) -> Path:
    root = _journal_root(journal_dir)
    created_at = _iso_now()
    session_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{int(time.time_ns() % 1_000_000):06d}"
    session_dir = root / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    latest_params = session_dir / "latest.params.json"
    session_json = session_dir / "session.json"
    preview_meta_path = session_dir / "preview.metadata.json"
    preview_meta = augment_visual_bloom_preview_metadata(source="session")

    session_doc: dict[str, object] = {
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": created_at,
        "mode": mode,
        "label": label,
        "collection": collection,
        "tags": normalize_visual_bloom_tags(tags),
        "seed": params.get("seed"),
        "refreshSeconds": refresh_seconds,
        "driftBand": params.get("driftBand"),
        "preset": params.get("preset", "none"),
        "lens": params.get("lens", "none"),
        "audioReactive": bool(params.get("audioReactive", False)),
        "source_command": source_command,
        "artifact_paths": {"html": str(output_path), "latest_params": str(latest_params), "preview_metadata": str(preview_meta_path)},
        "preview": preview_meta,
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
    preview_meta_path.write_text(json.dumps(preview_meta, indent=2), encoding="utf-8")
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
        preview = doc.get("preview") if isinstance(doc.get("preview"), dict) else augment_visual_bloom_preview_metadata(source="session", status="unknown")
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
                "preview": preview,
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
    state_records = session.get("states")
    state_total = len(state_records) if isinstance(state_records, list) else 1
    merged.setdefault("sessionId", str(session.get("session_id", "replay")))
    merged.setdefault("sessionLabel", str(session.get("label", "")))
    merged.setdefault("collection", str(session.get("collection", "")))
    merged.setdefault("preset", str(session.get("preset", "none")))
    merged.setdefault("lens", str(session.get("lens", "none")))
    merged.setdefault("stateIndex", idx)
    merged.setdefault("stateTotal", state_total)
    return merged


def select_visual_bloom_state(session: dict[str, object], state_idx: int | None = None) -> tuple[dict[str, object], int, int]:
    """Select a state by index from a session; defaults to latest."""
    states = session.get("states")
    if not isinstance(states, list) or not states:
        raise VisualizerError("Session has no recorded states.")
    total = len(states)
    idx = total - 1 if state_idx is None else state_idx
    if idx < 0:
        idx = total + idx
    if idx < 0 or idx >= total:
        raise VisualizerError(f"State index out of range: {state_idx}")
    state = states[idx]
    if not isinstance(state, dict):
        raise VisualizerError(f"Malformed state at index {idx}")
    return dict(state), idx, total


def step_visual_bloom_state(session: dict[str, object], current_idx: int, direction: int) -> tuple[dict[str, object], int, int]:
    """Step +1/-1 across archived states with bounds checking."""
    target = current_idx + direction
    return select_visual_bloom_state(session, state_idx=target)


def compute_visual_bloom_diff_metrics(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    """Compute concise deterministic deltas between two archived visual states."""
    def num(d: dict[str, object], k: str, default: float = 0.0) -> float:
        return _to_float(d.get(k), default)

    out: dict[str, object] = {
        "delta_coherenceC": round(num(right, "coherenceC") - num(left, "coherenceC"), 6),
        "delta_frequency": round(num(right, "frequency") - num(left, "frequency"), 6),
        "delta_particleCount": int(round(num(right, "particleCount") - num(left, "particleCount"))),
        "delta_noiseScale": round(num(right, "noiseScale") - num(left, "noiseScale"), 6),
        "delta_goldenInf": round(num(right, "goldenInf", 1.618) - num(left, "goldenInf", 1.618), 6),
        "driftBand_transition": f"{left.get('driftBand', 'unknown')} -> {right.get('driftBand', 'unknown')}",
        "preset_transition": f"{left.get('preset', 'none')} -> {right.get('preset', 'none')}",
        "lens_transition": f"{left.get('lens', 'none')} -> {right.get('lens', 'none')}",
        "audio_transition": f"{left.get('audioStatus', 'off')} -> {right.get('audioStatus', 'off')}",
    }
    return out


def export_visual_bloom_compare_report(
    *,
    output_path: Path,
    left: dict[str, object],
    right: dict[str, object],
    diff: dict[str, object],
) -> Path:
    """Write a local JSON compare report bundle."""
    if output_path.suffix.lower() != ".json":
        raise VisualizerError("Compare report path must end with .json")
    if any(part == ".." for part in output_path.parts):
        raise VisualizerError("Refusing compare report path containing '..'")
    if output_path.exists() and output_path.is_dir():
        raise VisualizerError("Compare report output path points to a directory")

    bundle = {
        "export_version": "v1",
        "exported_at": _iso_now(),
        "source": "PhiOS Visual Bloom Compare Report",
        "left": left,
        "right": right,
        "diff_metrics": diff,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return output_path


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
    preview_meta_path = session_dir / "preview.metadata.json"
    preview_meta = augment_visual_bloom_preview_metadata(source="session")
    doc["artifact_paths"] = {"html": str(output_html), "latest_params": str(latest_params), "preview_metadata": str(preview_meta_path)}
    doc["preview"] = preview_meta
    doc["updated_at"] = _iso_now()
    session_json.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    latest_params.write_text(json.dumps(params, indent=2), encoding="utf-8")
    preview_meta_path.write_text(json.dumps(preview_meta, indent=2), encoding="utf-8")
    return latest_params


def _compare_sets_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "compare_sets"


def save_visual_bloom_compare_set(
    *,
    name: str,
    left_ref: str,
    right_ref: str,
    journal_dir: Path | None = None,
    report_path: Path | None = None,
    bundle_path: Path | None = None,
    label: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    safe_name = _sanitize_collection(name)
    root = _compare_sets_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_name}.json"
    payload = {
        "name": safe_name,
        "created_at": _iso_now(),
        "left_ref": left_ref,
        "right_ref": right_ref,
        "label": label or "",
        "latest_report_path": str(report_path) if report_path else "",
        "latest_bundle_path": str(bundle_path) if bundle_path else "",
        "tags": normalize_visual_bloom_tags(tags),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def list_visual_bloom_compare_sets(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _compare_sets_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for p in root.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        out.append({
            "name": data.get("name", p.stem),
            "created_at": data.get("created_at", ""),
            "left_ref": data.get("left_ref", ""),
            "right_ref": data.get("right_ref", ""),
            "label": data.get("label", ""),
            "latest_report_path": data.get("latest_report_path", ""),
            "latest_bundle_path": data.get("latest_bundle_path", ""),
            "tags": data.get("tags", []),
        })
    out.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return out


def load_visual_bloom_compare_set(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe_name = _sanitize_collection(name)
    path = _compare_sets_root(journal_dir) / f"{safe_name}.json"
    if not path.exists():
        raise VisualizerError(f"Compare set not found: {safe_name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualizerError(f"Compare set JSON is invalid: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise VisualizerError("Compare set document must be an object")
    return data


def filter_visual_bloom_gallery_entries(
    entries: list[dict[str, object]],
    *,
    search: str | None = None,
    mode: str | None = None,
    preset: str | None = None,
    lens: str | None = None,
    audio: str | None = None,
    label: str | None = None,
    session_id: str | None = None,
) -> list[dict[str, object]]:
    """Apply deterministic prefilters for static gallery generation."""
    needle = (search or "").strip().lower()
    mode_n = (mode or "").strip().lower()
    preset_n = (preset or "").strip().lower()
    lens_n = (lens or "").strip().lower()
    audio_n = (audio or "").strip().lower()
    label_n = (label or "").strip().lower()
    session_n = (session_id or "").strip().lower()

    out: list[dict[str, object]] = []
    for entry in entries:
        if mode_n and str(entry.get("mode", "")).lower() != mode_n:
            continue
        if preset_n and str(entry.get("preset", "")).lower() != preset_n:
            continue
        if lens_n and str(entry.get("lens", "")).lower() != lens_n:
            continue
        if audio_n and str(entry.get("audio", "")).lower() != audio_n:
            continue
        if label_n and label_n not in str(entry.get("label", "")).lower():
            continue
        if session_n and session_n not in str(entry.get("session_id", "")).lower():
            continue
        if needle:
            blob = " ".join(
                str(entry.get(k, ""))
                for k in ("session_id", "label", "collection", "mode", "preset", "lens", "audio", "created_at", "updated_at", "latest_timestamp")
            ).lower()
            if needle not in blob:
                continue
        out.append(entry)
    return out


def build_visual_bloom_gallery_model(
    *,
    journal_dir: Path | None = None,
    collection: str | None = None,
    search: str | None = None,
    mode: str | None = None,
    preset: str | None = None,
    lens: str | None = None,
    audio: str | None = None,
    label: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    sessions = list_visual_bloom_sessions(journal_dir=journal_dir, collection=collection)
    sessions = filter_visual_bloom_gallery_entries(
        sessions,
        search=search,
        mode=mode,
        preset=preset,
        lens=lens,
        audio=audio,
        label=label,
        session_id=session_id,
    )
    compares = list_visual_bloom_compare_sets(journal_dir=journal_dir)
    return {
        "generated_at": _iso_now(),
        "collection": collection or "",
        "search": search or "",
        "filters": {
            "mode": mode or "",
            "preset": preset or "",
            "lens": lens or "",
            "audio": audio or "",
            "label": label or "",
            "session_id": session_id or "",
        },
        "session_count": len(sessions),
        "compare_set_count": len(compares),
        "sessions": sessions,
        "compare_sets": compares,
    }


def render_visual_bloom_gallery_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_gallery.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load gallery template: {exc}") from exc
    html = template.replace("__PHIOS_GALLERY_MODEL_JSON__", json.dumps(model, separators=(",", ":")))
    return html


def launch_visual_bloom_gallery(
    *,
    output_path: Path | None = None,
    open_browser: bool = True,
    journal_dir: Path | None = None,
    collection: str | None = None,
    search: str | None = None,
    mode: str | None = None,
    preset: str | None = None,
    lens: str | None = None,
    audio: str | None = None,
    label: str | None = None,
    session_id: str | None = None,
) -> Path:
    model = build_visual_bloom_gallery_model(
        journal_dir=journal_dir,
        collection=collection,
        search=search,
        mode=mode,
        preset=preset,
        lens=lens,
        audio=audio,
        label=label,
        session_id=session_id,
    )
    html = render_visual_bloom_gallery_html(model)
    target = output_path or Path("/tmp/phios_bloom_gallery.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written


def compute_visual_bloom_bundle_hashes(base: Path, files: dict[str, str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, rel in files.items():
        path = base / rel
        if not path.exists() or not path.is_file():
            hashes[key] = ""
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[key] = digest
    return hashes


def write_visual_bloom_bundle_manifest(*, manifest_path: Path, payload: dict[str, object]) -> Path:
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def export_visual_bloom_bundle(
    *,
    left_ref: str,
    right_ref: str,
    output_path: Path,
    journal_dir: Path | None = None,
    with_integrity: bool = False,
    bundle_label: str | None = None,
) -> Path:
    base = output_path
    if base.suffix.lower() == ".json":
        base = base.with_suffix("")
    base.mkdir(parents=True, exist_ok=True)
    report_path = base / "compare_report.json"
    html_path = base / "compare.html"
    manifest_path = base / "bundle_manifest.json"
    preview_meta_path = base / "preview_image_metadata.json"

    launch_compare_bloom(left_ref, right_ref, output_path=html_path, open_browser=False, journal_dir=journal_dir, export_report_path=report_path)

    preview_meta = augment_visual_bloom_preview_metadata(source="bundle")
    preview_meta_path.write_text(json.dumps(preview_meta, indent=2), encoding="utf-8")

    included_files = {
        "report": str(report_path.name),
        "html": str(html_path.name),
        "preview_metadata": str(preview_meta_path.name),
    }
    file_hashes = compute_visual_bloom_bundle_hashes(base, included_files)

    manifest: dict[str, object] = {
        "bundle_version": "v1",
        "manifest_version": "v2",
        "bundle_type": "visual_bloom_compare",
        "bundle_label": bundle_label or "",
        "bundle_created_at": _iso_now(),
        "source_refs": {"left": left_ref, "right": right_ref},
        "included_files": included_files,
        "report_schema_version": "v1",
        "compatibility_version": "phase8+",
        "compatibility_notes": "Older archives/bundles without new fields remain supported with safe defaults.",
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": file_hashes if with_integrity else {},
        "preview": preview_meta,
    }
    write_visual_bloom_bundle_manifest(manifest_path=manifest_path, payload=manifest)
    return base


def _narratives_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "narratives"


def create_visual_bloom_narrative(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    collection: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    safe_name = _sanitize_collection(name)
    root = _narratives_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_name}.json"
    now = _iso_now()
    if path.exists():
        raise VisualizerError(f"Narrative already exists: {safe_name}")
    doc: dict[str, object] = {
        "narrative_name": safe_name,
        "created_at": now,
        "updated_at": now,
        "title": title or "",
        "summary": summary or "",
        "collection": collection or "",
        "tags": normalize_visual_bloom_tags(tags),
        "entries": [],
        "links": [],
        "artifact_paths": {},
    }
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def load_visual_bloom_narrative(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe_name = _sanitize_collection(name)
    path = _narratives_root(journal_dir) / f"{safe_name}.json"
    if not path.exists():
        raise VisualizerError(f"Narrative not found: {safe_name}")
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise VisualizerError(f"Narrative JSON is invalid: {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise VisualizerError("Narrative document must be an object")
    entries = doc.get('entries')
    if not isinstance(entries, list):
        doc['entries'] = []
    links = doc.get('links')
    if not isinstance(links, list):
        doc['links'] = []
    tags = doc.get('tags')
    if not isinstance(tags, list):
        doc['tags'] = []
    return doc


def list_visual_bloom_narratives(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _narratives_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in root.glob('*.json'):
        try:
            doc = json.loads(pth.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        entries = doc.get('entries')
        count = len(entries) if isinstance(entries, list) else 0
        out.append({
            'narrative_name': doc.get('narrative_name', pth.stem),
            'created_at': doc.get('created_at', ''),
            'updated_at': doc.get('updated_at', ''),
            'title': doc.get('title', ''),
            'summary': doc.get('summary', ''),
            'collection': doc.get('collection', ''),
            'entry_count': count,
            'tags': doc.get('tags', []),
            'link_count': len(doc.get('links', [])) if isinstance(doc.get('links'), list) else 0,
        })
    out.sort(key=lambda i: str(i.get('created_at', '')), reverse=True)
    return out


def add_visual_bloom_narrative_entry(
    *,
    name: str,
    journal_dir: Path | None = None,
    session_ref: str | None = None,
    compare_left: str | None = None,
    compare_right: str | None = None,
    compare_set: str | None = None,
    entry_title: str | None = None,
    entry_note: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    doc = load_visual_bloom_narrative(name, journal_dir=journal_dir)
    safe_name = _sanitize_collection(name)
    path = _narratives_root(journal_dir) / f"{safe_name}.json"

    kind = ''
    ref: dict[str, object] = {}
    if session_ref:
        kind = 'session'
        ref = {'session_ref': session_ref}
    elif compare_set:
        kind = 'compare_set'
        ref = {'compare_set': _sanitize_collection(compare_set)}
    elif compare_left and compare_right:
        kind = 'compare'
        ref = {'left_ref': compare_left, 'right_ref': compare_right}
    else:
        raise VisualizerError('Narrative entry requires --session, --compare <left> <right>, or --compare-set')

    entries = doc.get('entries')
    if not isinstance(entries, list):
        entries = []
    entry = {
        'entry_id': f"e{len(entries):03d}",
        'entry_type': kind,
        'title': entry_title or '',
        'note': entry_note or '',
        'created_at': _iso_now(),
        'tags': normalize_visual_bloom_tags(tags),
        **ref,
    }
    entries.append(entry)
    doc['entries'] = entries
    doc['updated_at'] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def add_visual_bloom_narrative_link(
    *,
    name: str,
    link_type: str,
    target_ref: str,
    journal_dir: Path | None = None,
    label: str | None = None,
    note: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    doc = load_visual_bloom_narrative(name, journal_dir=journal_dir)
    safe_name = _sanitize_collection(name)
    path = _narratives_root(journal_dir) / f"{safe_name}.json"
    links = doc.get('links')
    if not isinstance(links, list):
        links = []
    links.append({
        'link_id': f"l{len(links):03d}",
        'link_type': _sanitize_collection(link_type),
        'target_ref': target_ref,
        'label': label or '',
        'note': note or '',
        'tags': normalize_visual_bloom_tags(tags),
        'created_at': _iso_now(),
    })
    doc['links'] = links
    doc['updated_at'] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def resolve_visual_bloom_link_ref(
    *,
    link_type: str,
    target_ref: str,
    journal_dir: Path | None = None,
) -> dict[str, object]:
    kind = _sanitize_collection(link_type)
    if kind == 'narrative':
        doc = load_visual_bloom_narrative(target_ref, journal_dir=journal_dir)
        return {'link_type': 'narrative', 'target': doc.get('narrative_name', target_ref)}
    if kind == 'session':
        state = load_visual_bloom_state(target_ref, journal_dir=journal_dir)
        return {'link_type': 'session', 'target': state.get('sessionId', target_ref)}
    if kind == 'compare-set':
        comp = load_visual_bloom_compare_set(target_ref, journal_dir=journal_dir)
        return {'link_type': 'compare-set', 'target': target_ref, 'left_ref': comp.get('left_ref', ''), 'right_ref': comp.get('right_ref', '')}
    if kind == 'atlas':
        p = Path(target_ref).expanduser()
        manifest = p / 'atlas_manifest.json' if p.is_dir() else p
        if not manifest.exists():
            raise VisualizerError(f"Atlas reference not found: {target_ref}")
        return {'link_type': 'atlas', 'target': str(manifest)}
    raise VisualizerError(f"Unsupported link type: {link_type}")


def resolve_visual_bloom_narrative_entry(
    entry: dict[str, object],
    *,
    journal_dir: Path | None = None,
) -> dict[str, object]:
    kind = str(entry.get('entry_type', ''))
    if kind == 'session':
        session_ref = str(entry.get('session_ref', ''))
        if not session_ref:
            raise VisualizerError('Narrative session entry missing session_ref')
        state = load_visual_bloom_state(session_ref, journal_dir=journal_dir)
        return {'entry_type': 'session', 'state': state}
    if kind == 'compare_set':
        set_name = str(entry.get('compare_set', ''))
        data = load_visual_bloom_compare_set(set_name, journal_dir=journal_dir)
        left_ref = str(data.get('left_ref', ''))
        right_ref = str(data.get('right_ref', ''))
        if not left_ref or not right_ref:
            raise VisualizerError(f"Compare set '{set_name}' is missing refs")
        return {'entry_type': 'compare', 'left_ref': left_ref, 'right_ref': right_ref, 'compare_set': set_name}
    if kind == 'compare':
        left_ref = str(entry.get('left_ref', ''))
        right_ref = str(entry.get('right_ref', ''))
        if not left_ref or not right_ref:
            raise VisualizerError('Narrative compare entry missing refs')
        return {'entry_type': 'compare', 'left_ref': left_ref, 'right_ref': right_ref}
    raise VisualizerError(f"Unsupported narrative entry type: {kind}")




def build_visual_bloom_atlas_model(
    *,
    atlas_target: str = "theoretical",
    atlas_node: int | None = None,
    atlas_start_ref: str | None = None,
    atlas_max_l1_radius: int = 1,
    atlas_heat_mode: str = "target_proximity",
    journal_dir: Path | None = None,
) -> dict[str, object]:
    nodes = [list(n) for n in build_lattice_4d_nodes()]
    graph = build_golden_atlas_graph(nodes, max_l1_radius=max(1, atlas_max_l1_radius), max_neighbors=16)

    start_idx = 0
    if atlas_start_ref:
        state = load_visual_bloom_state(atlas_start_ref, journal_dir=journal_dir)
        point = [
            _to_float(state.get("coherenceC"), C_STAR_THEORETICAL),
            _to_float(state.get("frequency"), 7.83) / 40.0,
            _to_float(state.get("particleCount"), 1500.0) / 2500.0,
            _to_float(state.get("noiseScale"), 0.005) / 0.02,
        ]
        start_idx = nearest_lattice_node(nodes, point)

    target_mode = _sanitize_collection(atlas_target) or "theoretical"
    target_point: list[float] = [C_STAR_THEORETICAL] * 4
    if target_mode == "node":
        if atlas_node is None:
            raise VisualizerError("--atlas-target node requires --atlas-node <idx>")
        path = find_path_to_target(nodes, graph, start_idx=start_idx, target_idx=atlas_node, target_point=nodes[atlas_node])
        target_idx = atlas_node
        target_point = [float(v) for v in nodes[atlas_node]]
    elif target_mode == "bio_band":
        path = find_path_to_bio_band(nodes, graph, start_idx=start_idx)
        end_obj = path.get("end_idx")
        target_idx = int(end_obj) if isinstance(end_obj, int) else -1
        target_point = [BIO_VACUUM_TARGET] * 4
    else:
        target_idx = nearest_lattice_node(nodes, target_point)
        path = find_path_to_target(nodes, graph, start_idx=start_idx, target_idx=target_idx, target_point=target_point)
        target_mode = "theoretical"

    heat = compute_atlas_heat(nodes, graph, target_point=target_point, mode=atlas_heat_mode)
    summary = build_golden_atlas_summary(nodes=nodes, graph=graph, path_result=path, heat=heat, target_mode=target_mode)
    sector_weights = infer_visual_bloom_sector_weights({"coherenceC": target_point[0], "noiseScale": 0.005, "frequency": 7.83})

    raw_path = path.get("path")
    path_ids = raw_path if isinstance(raw_path, list) else []
    route = [nodes[i] for i in path_ids if isinstance(i, int) and 0 <= i < len(nodes)]
    return {
        "generated_at": _iso_now(),
        "experimental": True,
        "target_mode": target_mode,
        "start_idx": start_idx,
        "target_idx": target_idx,
        "path": path,
        "route_nodes": route,
        "route_length": len(route),
        "route_cost": _to_float(path.get("cost"), 0.0),
        "heat_mode": atlas_heat_mode,
        "heat_summary": {
            "min": min(heat) if heat else 0.0,
            "max": max(heat) if heat else 0.0,
            "avg": (sum(heat) / len(heat)) if heat else 0.0,
        },
        "summary": summary,
        "sector_family": "HG",
        "sector_weights": sector_weights,
        "dominant_sector": dominant_sector(sector_weights),
        "constants": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
    }


def render_visual_bloom_atlas_map_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_atlas_map.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load atlas map template: {exc}") from exc
    return template.replace("__PHIOS_ATLAS_MAP_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def launch_visual_bloom_atlas(
    *,
    output_path: Path | None = None,
    open_browser: bool = True,
    atlas_target: str = "theoretical",
    atlas_start_ref: str | None = None,
    atlas_node: int | None = None,
    atlas_max_l1_radius: int = 1,
    atlas_heat_mode: str = "target_proximity",
    journal_dir: Path | None = None,
) -> Path:
    model = build_visual_bloom_atlas_model(
        atlas_target=atlas_target,
        atlas_node=atlas_node,
        atlas_start_ref=atlas_start_ref,
        atlas_max_l1_radius=atlas_max_l1_radius,
        atlas_heat_mode=atlas_heat_mode,
        journal_dir=journal_dir,
    )
    html = render_visual_bloom_atlas_map_html(model)
    target = output_path or Path("/tmp/phios_bloom_atlas.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written

def render_visual_bloom_atlas_html(model: dict[str, object]) -> str:
    try:
        template = resources.files('phios.templates').joinpath('sonic_atlas.html').read_text(encoding='utf-8')
    except Exception as exc:
        raise VisualizerError(f"Unable to load atlas template: {exc}") from exc
    return template.replace('__PHIOS_ATLAS_MODEL_JSON__', json.dumps(model, separators=(',', ':')))


def export_visual_bloom_atlas(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    with_integrity: bool = False,
    tags: str | list[str] | None = None,
) -> Path:
    narrative = load_visual_bloom_narrative(name, journal_dir=journal_dir)
    atlas_dir = output_dir.expanduser()
    atlas_dir.mkdir(parents=True, exist_ok=True)
    entries_dir = atlas_dir / 'entries'
    entries_dir.mkdir(parents=True, exist_ok=True)

    raw_entries = narrative.get('entries')
    entries = raw_entries if isinstance(raw_entries, list) else []
    atlas_entries: list[dict[str, object]] = []

    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        resolved = resolve_visual_bloom_narrative_entry(item, journal_dir=journal_dir)
        entry_json = entries_dir / f'entry_{idx:03d}.json'
        entry_html = entries_dir / f'entry_{idx:03d}.html'
        entry_meta: dict[str, object] = {
            'index': idx,
            'entry': item,
            'resolved': {},
            'artifact_paths': {'json': str(entry_json.name), 'html': str(entry_html.name)},
        }

        if resolved.get('entry_type') == 'session':
            state_obj = resolved.get('state')
            state = dict(state_obj) if isinstance(state_obj, dict) else {}
            state['mode'] = 'replay'
            html = render_bloom_html(state, live_mode=False)
            write_bloom_file(html, entry_html)
            entry_meta['resolved'] = {'entry_type': 'session', 'session_ref': item.get('session_ref', ''), 'stateTimestamp': state.get('stateTimestamp', '')}
        else:
            left_ref = str(resolved.get('left_ref', ''))
            right_ref = str(resolved.get('right_ref', ''))
            left_session, left_state, _ = resolve_visual_bloom_state_ref(left_ref, journal_dir=journal_dir)
            right_session, right_state, _ = resolve_visual_bloom_state_ref(right_ref, journal_dir=journal_dir)
            left_params = _with_live_contract(dict(left_state), mode='compare-left', session_id=str(left_session.get('session_id', 'left')))
            right_params = _with_live_contract(dict(right_state), mode='compare-right', session_id=str(right_session.get('session_id', 'right')))
            diff = compute_visual_bloom_diff_metrics(left_params, right_params)
            html = render_compare_bloom_html(left_params, right_params, diff)
            write_bloom_file(html, entry_html)
            entry_meta['resolved'] = {'entry_type': 'compare', 'left_ref': left_ref, 'right_ref': right_ref, 'diff': diff}

        entry_json.write_text(json.dumps(entry_meta, indent=2), encoding='utf-8')
        resolved_meta = entry_meta.get('resolved')
        resolved_dict = resolved_meta if isinstance(resolved_meta, dict) else {}
        atlas_entries.append({
            'index': idx,
            'entry_type': str(resolved_dict.get('entry_type', '')),
            'title': item.get('title', ''),
            'note': item.get('note', ''),
            'json': str(Path('entries') / entry_json.name),
            'html': str(Path('entries') / entry_html.name),
        })

    atlas_model = {
        'narrative_name': narrative.get('narrative_name', _sanitize_collection(name)),
        'title': narrative.get('title', ''),
        'summary': narrative.get('summary', ''),
        'created_at': narrative.get('created_at', ''),
        'updated_at': narrative.get('updated_at', ''),
        'exported_at': _iso_now(),
        'entry_count': len(atlas_entries),
        'entries': atlas_entries,
    }
    atlas_html = render_visual_bloom_atlas_html(atlas_model)
    write_bloom_file(atlas_html, atlas_dir / 'atlas_index.html')

    included_files = {
        'atlas_index': 'atlas_index.html',
        'narrative_source': 'narrative.json',
    }
    for e in atlas_entries:
        idx_val = str(e.get('index', ''))
        included_files[f"entry_json_{idx_val}"] = str(e.get('json', ''))
        included_files[f"entry_html_{idx_val}"] = str(e.get('html', ''))

    file_hashes = compute_visual_bloom_bundle_hashes(atlas_dir, included_files)
    preview_meta = augment_visual_bloom_preview_metadata(source='atlas')
    (atlas_dir / 'preview_image_metadata.json').write_text(json.dumps(preview_meta, indent=2), encoding='utf-8')

    narrative_copy = dict(narrative)
    narrative_copy['artifact_paths'] = {'atlas_dir': str(atlas_dir)}
    (atlas_dir / 'narrative.json').write_text(json.dumps(narrative_copy, indent=2), encoding='utf-8')

    manifest: dict[str, object] = {
        'atlas_version': 'v1',
        'manifest_version': 'v1',
        'atlas_type': 'visual_bloom_field_atlas',
        'narrative_name': atlas_model['narrative_name'],
        'bundle_created_at': atlas_model['exported_at'],
        'entry_count': len(atlas_entries),
        'tags': atlas_model.get('tags', []),
        'included_files': included_files,
        'integrity_mode': 'sha256' if with_integrity else 'none',
        'file_hashes_sha256': file_hashes if with_integrity else {},
        'preview': preview_meta,
        'compatibility_version': 'phase10+',
        'compatibility_notes': 'Additive schema; older archives/bundles remain supported with safe defaults.',
    }
    write_visual_bloom_bundle_manifest(manifest_path=atlas_dir / 'atlas_manifest.json', payload=manifest)
    return atlas_dir



def _constellations_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / 'constellations'


def create_visual_bloom_constellation(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    safe_name = _sanitize_collection(name)
    root = _constellations_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_name}.json"
    if path.exists():
        raise VisualizerError(f"Constellation already exists: {safe_name}")
    now = _iso_now()
    doc = {
        'constellation_name': safe_name,
        'created_at': now,
        'updated_at': now,
        'title': title or '',
        'summary': summary or '',
        'tags': normalize_visual_bloom_tags(tags),
        'entries': [],
        'links': [],
        'artifact_paths': {},
    }
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def load_visual_bloom_constellation(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe_name = _sanitize_collection(name)
    path = _constellations_root(journal_dir) / f"{safe_name}.json"
    if not path.exists():
        raise VisualizerError(f"Constellation not found: {safe_name}")
    doc = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(doc, dict):
        raise VisualizerError('Constellation document must be an object')
    if not isinstance(doc.get('entries'), list):
        doc['entries'] = []
    if not isinstance(doc.get('links'), list):
        doc['links'] = []
    if not isinstance(doc.get('tags'), list):
        doc['tags'] = []
    return doc


def list_visual_bloom_constellations(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _constellations_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in root.glob('*.json'):
        try:
            doc = json.loads(pth.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        entries = doc.get('entries')
        links = doc.get('links')
        out.append({
            'constellation_name': doc.get('constellation_name', pth.stem),
            'created_at': doc.get('created_at', ''),
            'updated_at': doc.get('updated_at', ''),
            'title': doc.get('title', ''),
            'summary': doc.get('summary', ''),
            'tags': doc.get('tags', []),
            'entry_count': len(entries) if isinstance(entries, list) else 0,
            'link_count': len(links) if isinstance(links, list) else 0,
        })
    out.sort(key=lambda i: str(i.get('created_at', '')), reverse=True)
    return out


def add_visual_bloom_constellation_entry(
    *,
    name: str,
    journal_dir: Path | None = None,
    narrative_ref: str | None = None,
    session_ref: str | None = None,
    compare_set: str | None = None,
    compare_left: str | None = None,
    compare_right: str | None = None,
    entry_title: str | None = None,
    entry_note: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    doc = load_visual_bloom_constellation(name, journal_dir=journal_dir)
    safe_name = _sanitize_collection(name)
    path = _constellations_root(journal_dir) / f"{safe_name}.json"
    entries = doc.get('entries')
    if not isinstance(entries, list):
        entries = []

    if narrative_ref:
        entry_type = 'narrative'
        ref = {'narrative_ref': _sanitize_collection(narrative_ref)}
    elif session_ref:
        entry_type = 'session'
        ref = {'session_ref': session_ref}
    elif compare_set:
        entry_type = 'compare_set'
        ref = {'compare_set': _sanitize_collection(compare_set)}
    elif compare_left and compare_right:
        entry_type = 'compare'
        ref = {'left_ref': compare_left, 'right_ref': compare_right}
    else:
        raise VisualizerError('Constellation entry requires --narrative, --session, --compare-set, or --compare <left> <right>')

    entries.append({
        'entry_id': f"c{len(entries):03d}",
        'entry_type': entry_type,
        'title': entry_title or '',
        'note': entry_note or '',
        'tags': normalize_visual_bloom_tags(tags),
        'created_at': _iso_now(),
        **ref,
    })
    doc['entries'] = entries
    doc['updated_at'] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def render_visual_bloom_constellation_html(model: dict[str, object]) -> str:
    try:
        template = resources.files('phios.templates').joinpath('sonic_constellation.html').read_text(encoding='utf-8')
    except Exception as exc:
        raise VisualizerError(f"Unable to load constellation template: {exc}") from exc
    return template.replace('__PHIOS_CONSTELLATION_MODEL_JSON__', json.dumps(model, separators=(',', ':')))


def export_visual_bloom_constellation(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    with_integrity: bool = False,
    tags: str | list[str] | None = None,
) -> Path:
    const = load_visual_bloom_constellation(name, journal_dir=journal_dir)
    out_dir = output_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries_dir = out_dir / 'items'
    entries_dir.mkdir(parents=True, exist_ok=True)

    raw_entries = const.get('entries')
    entries = raw_entries if isinstance(raw_entries, list) else []
    rendered: list[dict[str, object]] = []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        et = str(entry.get('entry_type', ''))
        resolved: dict[str, object]
        if et == 'narrative':
            nref = str(entry.get('narrative_ref', ''))
            ndoc = load_visual_bloom_narrative(nref, journal_dir=journal_dir)
            resolved = {'entry_type': 'narrative', 'target': ndoc.get('narrative_name', nref), 'title': ndoc.get('title', ''), 'tags': ndoc.get('tags', [])}
        elif et == 'session':
            sref = str(entry.get('session_ref', ''))
            st = load_visual_bloom_state(sref, journal_dir=journal_dir)
            resolved = {'entry_type': 'session', 'target': st.get('sessionId', sref), 'stateTimestamp': st.get('stateTimestamp', '')}
        elif et == 'compare_set':
            cref = str(entry.get('compare_set', ''))
            comp = load_visual_bloom_compare_set(cref, journal_dir=journal_dir)
            resolved = {'entry_type': 'compare_set', 'target': cref, 'left_ref': comp.get('left_ref', ''), 'right_ref': comp.get('right_ref', ''), 'tags': comp.get('tags', [])}
        elif et == 'compare':
            left_ref = str(entry.get('left_ref', ''))
            right_ref = str(entry.get('right_ref', ''))
            if not left_ref or not right_ref:
                raise VisualizerError('Constellation compare entry missing refs')
            resolved = {'entry_type': 'compare', 'left_ref': left_ref, 'right_ref': right_ref}
        else:
            raise VisualizerError(f"Unsupported constellation entry type: {et}")

        entry_json = entries_dir / f'item_{idx:03d}.json'
        payload = {'index': idx, 'entry': entry, 'resolved': resolved}
        entry_json.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        rendered.append({'index': idx, 'entry_type': et, 'title': entry.get('title', ''), 'note': entry.get('note', ''), 'tags': entry.get('tags', []), 'json': str(Path('items') / entry_json.name), 'resolved': resolved})

    links_raw = const.get('links')
    links = links_raw if isinstance(links_raw, list) else []
    link_summaries: list[dict[str, object]] = []
    for lk in links:
        if not isinstance(lk, dict):
            continue
        ltype = str(lk.get('link_type', ''))
        tref = str(lk.get('target_ref', ''))
        try:
            resolved = resolve_visual_bloom_link_ref(link_type=ltype, target_ref=tref, journal_dir=journal_dir)
            status = 'resolved'
        except VisualizerError:
            resolved = {'link_type': ltype, 'target': tref}
            status = 'unresolved'
        link_summaries.append({'link_type': ltype, 'target_ref': tref, 'label': lk.get('label', ''), 'note': lk.get('note', ''), 'tags': lk.get('tags', []), 'status': status, 'resolved': resolved})

    model = {
        'constellation_name': const.get('constellation_name', _sanitize_collection(name)),
        'title': const.get('title', ''),
        'summary': const.get('summary', ''),
        'tags': normalize_visual_bloom_tags(tags) or const.get('tags', []),
        'created_at': const.get('created_at', ''),
        'updated_at': const.get('updated_at', ''),
        'exported_at': _iso_now(),
        'entry_count': len(rendered),
        'link_count': len(link_summaries),
        'entries': rendered,
        'links': link_summaries,
    }
    html = render_visual_bloom_constellation_html(model)
    write_bloom_file(html, out_dir / 'constellation_index.html')
    (out_dir / 'constellation.json').write_text(json.dumps(const, indent=2), encoding='utf-8')
    preview = augment_visual_bloom_preview_metadata(source='constellation')
    (out_dir / 'preview_image_metadata.json').write_text(json.dumps(preview, indent=2), encoding='utf-8')

    included = {'index': 'constellation_index.html', 'constellation': 'constellation.json', 'preview': 'preview_image_metadata.json'}
    for item in rendered:
        included[f"item_{item['index']}"] = str(item.get('json', ''))
    hashes = compute_visual_bloom_bundle_hashes(out_dir, included)
    manifest = {
        'constellation_version': 'v1',
        'manifest_version': 'v1',
        'constellation_type': 'visual_bloom_constellation',
        'constellation_name': model['constellation_name'],
        'bundle_created_at': model['exported_at'],
        'entry_count': len(rendered),
        'link_count': len(link_summaries),
        'tags': model['tags'],
        'included_files': included,
        'integrity_mode': 'sha256' if with_integrity else 'none',
        'file_hashes_sha256': hashes if with_integrity else {},
        'preview': preview,
        'compatibility_version': 'phase11+',
        'compatibility_notes': 'Additive schema; older artifacts remain supported with safe defaults.',
    }
    write_visual_bloom_bundle_manifest(manifest_path=out_dir / 'constellation_manifest.json', payload=manifest)
    return out_dir





def _storyboards_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "storyboards"


def create_visual_bloom_storyboard(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: str | list[str] | None = None,
    filters: dict[str, object] | None = None,
) -> Path:
    safe = _sanitize_collection(name)
    if not safe:
        raise VisualizerError("Storyboard name is required")
    root = _storyboards_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe}.json"
    if path.exists():
        raise VisualizerError(f"Storyboard '{safe}' already exists")
    doc = {
        "storyboard_name": safe,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "title": title or safe,
        "summary": summary or "",
        "tags": normalize_visual_bloom_tags(tags),
        "filters": filters or {},
        "sections": [],
        "artifact_refs": [],
        "generated_artifact_paths": {},
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def list_visual_bloom_storyboards(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _storyboards_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in sorted(root.glob("*.json")):
        try:
            doc = json.loads(pth.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        sections = doc.get("sections")
        out.append({
            "storyboard_name": doc.get("storyboard_name", pth.stem),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at", ""),
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "tags": doc.get("tags", []),
            "section_count": len(sections) if isinstance(sections, list) else 0,
        })
    out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return out


def load_visual_bloom_storyboard(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe = _sanitize_collection(name)
    path = _storyboards_root(journal_dir) / f"{safe}.json"
    if not path.exists():
        raise VisualizerError(f"Storyboard not found: {name}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VisualizerError(f"Invalid storyboard JSON '{name}': {exc}") from exc
    if not isinstance(doc, dict):
        raise VisualizerError("Storyboard payload must be an object")
    return doc


def add_visual_bloom_storyboard_section(
    *,
    name: str,
    section_type: str,
    artifact_ref: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    tags: str | list[str] | None = None,
    sector_family: str | None = None,
) -> Path:
    doc = load_visual_bloom_storyboard(name, journal_dir=journal_dir)
    safe = _sanitize_collection(name)
    path = _storyboards_root(journal_dir) / f"{safe}.json"
    sections_obj = doc.get("sections")
    sections = sections_obj if isinstance(sections_obj, list) else []
    stype = _sanitize_collection(section_type)
    if stype not in {"insight_pack", "branch_replay", "route_compare", "pathway", "atlas", "narrative", "constellation"}:
        raise VisualizerError("Unsupported storyboard section type")

    sec_summary = build_visual_bloom_sector_summary(metadata={"tags": normalize_visual_bloom_tags(tags)}, family=sector_family or "HG")
    section = {
        "section_id": f"s{len(sections):03d}",
        "section_type": stype,
        "title": title or stype,
        "summary": summary or "",
        "artifact_ref": artifact_ref,
        "notes": notes or "",
        "tags": normalize_visual_bloom_tags(tags),
        "sector_overlay": sec_summary,
        "diagnostics_ref": "",
    }
    sections.append(section)
    doc["sections"] = sections
    refs_obj = doc.get("artifact_refs")
    refs = refs_obj if isinstance(refs_obj, list) else []
    refs.append({"type": stype, "ref": artifact_ref})
    doc["artifact_refs"] = refs
    doc["updated_at"] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def _storyboard_section_matches_filters(section: dict[str, object], filters: dict[str, object]) -> bool:
    tags_req_obj = filters.get("tags")
    tags_req = set(normalize_visual_bloom_tags(tags_req_obj if isinstance(tags_req_obj, (str, list)) else None)) if tags_req_obj else set()
    type_obj = filters.get("type")
    sector_obj = filters.get("sector")
    stype = _sanitize_collection(type_obj) if isinstance(type_obj, str) else ""
    sector = _sanitize_collection(sector_obj) if isinstance(sector_obj, str) else ""
    sec_tags_obj = section.get("tags")
    sec_tags = {str(t) for t in sec_tags_obj if str(t)} if isinstance(sec_tags_obj, list) else set()
    if tags_req and not tags_req.issubset(sec_tags):
        return False
    if stype and _sanitize_collection(str(section.get("section_type", ""))) != stype:
        return False
    if sector:
        so = section.get("sector_overlay")
        sd = so if isinstance(so, dict) else {}
        if _sanitize_collection(str(sd.get("dominant_sector", ""))) != sector:
            return False
    return True


def build_visual_bloom_comparative_summary(*, sections: list[dict[str, object]]) -> dict[str, object]:
    type_counts: dict[str, int] = {}
    dominant_counts: dict[str, int] = {}
    for sec in sections:
        st = _sanitize_collection(str(sec.get("section_type", "")))
        type_counts[st] = type_counts.get(st, 0) + 1
        so = sec.get("sector_overlay")
        sd = so if isinstance(so, dict) else {}
        dom = _sanitize_collection(str(sd.get("dominant_sector", "")))
        if dom:
            dominant_counts[dom] = dominant_counts.get(dom, 0) + 1
    return {
        "section_count": len(sections),
        "section_type_counts": type_counts,
        "dominant_sector_counts": dominant_counts,
        "interpretive_note": "Comparative summary is an experimental local observatory synthesis.",
    }


def build_visual_bloom_storyboard_model(
    *,
    name: str,
    journal_dir: Path | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
) -> dict[str, object]:
    doc = load_visual_bloom_storyboard(name, journal_dir=journal_dir)
    sections_obj = doc.get("sections")
    sections = [s for s in sections_obj if isinstance(s, dict)] if isinstance(sections_obj, list) else []
    filters: dict[str, object] = {
        "tags": filter_tags,
        "sector": filter_sector,
        "type": filter_type,
    }
    selected = [s for s in sections if _storyboard_section_matches_filters(s, filters)]
    comparative = build_visual_bloom_comparative_summary(sections=selected)
    timeline = build_visual_bloom_route_timeline(model={**doc, "sections": selected})
    return {
        **doc,
        "filters": filters,
        "sections": selected,
        "comparative_summary": comparative,
        "route_timeline": timeline,
        "generated_at": _iso_now(),
        "experimental": True,
    }


def render_visual_bloom_storyboard_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_storyboard.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load storyboard template: {exc}") from exc
    return template.replace("__PHIOS_STORYBOARD_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_storyboard(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    title: str | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    model = build_visual_bloom_storyboard_model(
        name=name,
        journal_dir=journal_dir,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
    )
    if title:
        model["title"] = title
    html = render_visual_bloom_storyboard_html(model)
    write_bloom_file(html, out / "storyboard_index.html")
    (out / "storyboard.json").write_text(json.dumps(model, indent=2), encoding="utf-8")

    timeline = build_visual_bloom_route_timeline(model=model)
    (out / "route_timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")

    sec_dir = out / "sections"
    sec_dir.mkdir(parents=True, exist_ok=True)
    sections_obj = model.get("sections")
    sections = sections_obj if isinstance(sections_obj, list) else []
    for idx, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        (sec_dir / f"section_{idx:03d}.json").write_text(json.dumps(sec, indent=2), encoding="utf-8")

    (out / "comparative_summary.json").write_text(json.dumps(model.get("comparative_summary", {}), indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="storyboard")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    included = {
        "index": "storyboard_index.html",
        "storyboard": "storyboard.json",
        "route_timeline": "route_timeline.json",
        "comparative_summary": "comparative_summary.json",
        "preview": "preview_image_metadata.json",
    }
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "storyboard_version": "v1",
        "type": "visual_bloom_storyboard",
        "storyboard_name": model.get("storyboard_name", name),
        "generated_at": model.get("generated_at", _iso_now()),
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase17+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "storyboard_manifest.json", payload=manifest)
    return out


def _dossiers_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "dossiers"


def create_visual_bloom_dossier(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: str | list[str] | None = None,
    filters: dict[str, object] | None = None,
) -> Path:
    safe = _sanitize_collection(name)
    root = _dossiers_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe}.json"
    if path.exists():
        raise VisualizerError(f"Dossier '{safe}' already exists")
    now = _iso_now()
    doc = {
        "dossier_name": safe,
        "created_at": now,
        "updated_at": now,
        "title": title or safe,
        "summary": summary or "",
        "tags": normalize_visual_bloom_tags(tags),
        "filters": filters or {},
        "sections": [],
        "artifact_refs": [],
        "generated_artifact_paths": {},
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def list_visual_bloom_dossiers(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _dossiers_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in sorted(root.glob("*.json")):
        doc = _safe_load_json(pth)
        if not doc:
            continue
        sections = doc.get("sections")
        out.append({
            "dossier_name": doc.get("dossier_name", pth.stem),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at", ""),
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "tags": doc.get("tags", []),
            "section_count": len(sections) if isinstance(sections, list) else 0,
        })
    out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return out


def load_visual_bloom_dossier(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe = _sanitize_collection(name)
    path = _dossiers_root(journal_dir) / f"{safe}.json"
    doc = _safe_load_json(path)
    if not doc:
        raise VisualizerError(f"Dossier not found or invalid: {name}")
    return doc


def add_visual_bloom_dossier_section(
    *,
    name: str,
    section_type: str,
    artifact_ref: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    tags: str | list[str] | None = None,
    sector_family: str | None = None,
) -> Path:
    doc = load_visual_bloom_dossier(name, journal_dir=journal_dir)
    safe = _sanitize_collection(name)
    path = _dossiers_root(journal_dir) / f"{safe}.json"
    stype = _sanitize_collection(section_type)
    allowed = {
        "storyboard", "route_compare", "atlas_gallery", "longitudinal", "insight_pack",
        "pathway", "atlas", "narrative", "constellation",
    }
    if stype not in allowed:
        raise VisualizerError("Unsupported dossier section type")
    sections_obj = doc.get("sections")
    sections = sections_obj if isinstance(sections_obj, list) else []
    sec_summary = build_visual_bloom_sector_summary(metadata={"tags": normalize_visual_bloom_tags(tags)}, family=sector_family or "HG")
    section = {
        "section_id": f"d{len(sections):03d}",
        "section_type": stype,
        "title": title or stype,
        "summary": summary or "",
        "artifact_ref": artifact_ref,
        "notes": notes or "",
        "tags": normalize_visual_bloom_tags(tags),
        "sector_overlay": sec_summary,
        "diagnostics_ref": "",
        "route_context": {},
        "timeline_context": {},
    }
    sections.append(section)
    doc["sections"] = sections
    refs_obj = doc.get("artifact_refs")
    refs = refs_obj if isinstance(refs_obj, list) else []
    refs.append({"type": stype, "ref": artifact_ref})
    doc["artifact_refs"] = refs
    doc["updated_at"] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def build_visual_bloom_dossier_candidates(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sb in list_visual_bloom_storyboards(journal_dir=journal_dir):
        rows.append({
            "artifact_type": "storyboard",
            "artifact_ref": str(_storyboards_root(journal_dir) / f"{_sanitize_collection(str(sb.get('storyboard_name', '')))}.json"),
            "title": sb.get("title", ""),
            "tags": sb.get("tags", []),
            "created_at": sb.get("created_at", ""),
            "dominant_sector": "",
            "sector_family": "",
            "target_mode": "",
            "heat_mode": "",
            "has_bio": False,
            "has_route_compare": False,
            "has_diagnostics": False,
        })
    for path in _scan_manifest_files(journal_dir=journal_dir, name="route_compare_manifest.json"):
        manifest = _safe_load_json(path)
        if not manifest:
            continue
        rows.append({
            "artifact_type": "route_compare",
            "artifact_ref": str(path.parent),
            "title": manifest.get("title", ""),
            "tags": manifest.get("tags", []),
            "created_at": manifest.get("generated_at", ""),
            "dominant_sector": "",
            "sector_family": "hg",
            "target_mode": "theoretical_vs_bio_band",
            "heat_mode": manifest.get("heat_mode", ""),
            "has_bio": True,
            "has_route_compare": True,
            "has_diagnostics": True,
        })
    for path in _scan_manifest_files(journal_dir=journal_dir, name="longitudinal_manifest.json"):
        manifest = _safe_load_json(path)
        if not manifest:
            continue
        rows.append({
            "artifact_type": "longitudinal",
            "artifact_ref": str(path.parent),
            "title": manifest.get("title", ""),
            "tags": manifest.get("tags", []),
            "created_at": manifest.get("generated_at", ""),
            "dominant_sector": "",
            "sector_family": "",
            "target_mode": "",
            "heat_mode": "",
            "has_bio": True,
            "has_route_compare": False,
            "has_diagnostics": False,
        })
    return rows


def filter_visual_bloom_dossier_candidates(
    *,
    candidates: list[dict[str, object]],
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
) -> list[dict[str, object]]:
    tags_req = set(normalize_visual_bloom_tags(filter_tags)) if filter_tags else set()
    sector = str(filter_sector or "").strip().lower().replace(" ", "_")
    ctype = _sanitize_collection(filter_type) if filter_type else ""
    target = _sanitize_collection(filter_target) if filter_target else ""
    if target and target not in {"theoretical", "bio_band", "node"}:
        raise VisualizerError("Invalid dossier target filter. Use theoretical|bio_band|node")
    out: list[dict[str, object]] = []
    for row in candidates:
        tags_obj = row.get("tags")
        tags = normalize_visual_bloom_tags(tags_obj if isinstance(tags_obj, (str, list)) else None)
        if tags_req and not tags_req.issubset(set(tags)):
            continue
        if sector and str(row.get("dominant_sector", "")).strip().lower().replace(" ", "_") != sector:
            continue
        if ctype and _sanitize_collection(str(row.get("artifact_type", ""))) != ctype:
            continue
        if target and target not in str(row.get("target_mode", "")).lower():
            continue
        out.append(row)
    return out


def build_visual_bloom_dossier_summary(*, sections: list[dict[str, object]]) -> dict[str, object]:
    type_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    coverage = {
        "route_compare": 0,
        "storyboard_timeline": 0,
        "longitudinal": 0,
        "diagnostics": 0,
    }
    for sec in sections:
        st = _sanitize_collection(str(sec.get("section_type", "")))
        if st:
            type_counts[st] = type_counts.get(st, 0) + 1
        so = sec.get("sector_overlay")
        sd = so if isinstance(so, dict) else {}
        dom = str(sd.get("dominant_sector", "")).strip().lower().replace(" ", "_")
        if dom:
            sector_counts[dom] = sector_counts.get(dom, 0) + 1
        rc = sec.get("route_context")
        rcd = rc if isinstance(rc, dict) else {}
        target = _sanitize_collection(str(rcd.get("target_mode", ""))) if rcd.get("target_mode") else ""
        if target:
            target_counts[target] = target_counts.get(target, 0) + 1
        tags_obj = sec.get("tags")
        tags = normalize_visual_bloom_tags(tags_obj if isinstance(tags_obj, (str, list)) else None)
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if st == "route_compare":
            coverage["route_compare"] += 1
        if st == "storyboard":
            coverage["storyboard_timeline"] += 1
        if st == "longitudinal":
            coverage["longitudinal"] += 1
        if sec.get("diagnostics_ref"):
            coverage["diagnostics"] += 1
    return {
        "summary_version": "v1",
        "section_count": len(sections),
        "artifact_type_counts": type_counts,
        "dominant_sector_counts": sector_counts,
        "route_target_mode_counts": target_counts,
        "tag_coverage": tag_counts,
        "coverage": coverage,
        "interpretive_note": "Dossier summaries are deterministic local curation layers and do not validate physical laws.",
    }


def build_visual_bloom_dossier_model(
    *,
    name: str,
    journal_dir: Path | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
) -> dict[str, object]:
    doc = load_visual_bloom_dossier(name, journal_dir=journal_dir)
    sections_obj = doc.get("sections")
    sections = [s for s in sections_obj if isinstance(s, dict)] if isinstance(sections_obj, list) else []
    candidates = build_visual_bloom_dossier_candidates(journal_dir=journal_dir)
    curated = filter_visual_bloom_dossier_candidates(
        candidates=candidates,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
        filter_target=filter_target,
    )
    filters = {
        "tags": filter_tags or "",
        "sector": filter_sector or "",
        "type": filter_type or "",
        "target": filter_target or "",
    }
    summary = build_visual_bloom_dossier_summary(sections=sections)
    return {
        **doc,
        "filters": filters,
        "sections": sections,
        "dossier_summary": summary,
        "curated_candidates": curated,
        "generated_at": _iso_now(),
        "experimental": True,
    }


def render_visual_bloom_dossier_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_dossier.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load dossier template: {exc}") from exc
    return template.replace("__PHIOS_DOSSIER_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_dossier(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    title: str | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    model = build_visual_bloom_dossier_model(
        name=name,
        journal_dir=journal_dir,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
        filter_target=filter_target,
    )
    if title:
        model["title"] = title
    html = render_visual_bloom_dossier_html(model)
    write_bloom_file(html, out / "dossier_index.html")
    (out / "dossier.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    sec_dir = out / "sections"
    sec_dir.mkdir(parents=True, exist_ok=True)
    sections_obj = model.get("sections")
    sections = sections_obj if isinstance(sections_obj, list) else []
    for idx, sec in enumerate(sections):
        if isinstance(sec, dict):
            (sec_dir / f"section_{idx:03d}.json").write_text(json.dumps(sec, indent=2), encoding="utf-8")
    dsum_obj = model.get("dossier_summary")
    dsum = dsum_obj if isinstance(dsum_obj, dict) else {}
    (out / "dossier_summary.json").write_text(json.dumps(dsum, indent=2), encoding="utf-8")
    (out / "route_context_summary.json").write_text(json.dumps(dsum.get("route_target_mode_counts", {}), indent=2), encoding="utf-8")
    (out / "sector_summary.json").write_text(json.dumps(dsum.get("dominant_sector_counts", {}), indent=2), encoding="utf-8")
    (out / "diagnostics_summary.json").write_text(json.dumps(dsum.get("coverage", {}), indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="dossier")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")
    included = {
        "index": "dossier_index.html",
        "dossier": "dossier.json",
        "dossier_summary": "dossier_summary.json",
        "sector_summary": "sector_summary.json",
        "diagnostics_summary": "diagnostics_summary.json",
        "route_context_summary": "route_context_summary.json",
        "preview": "preview_image_metadata.json",
    }
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "dossier_version": "v1",
        "type": "visual_bloom_dossier",
        "dossier_name": model.get("dossier_name", name),
        "generated_at": model.get("generated_at", _iso_now()),
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase19+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "dossier_manifest.json", payload=manifest)
    return out


def _field_libraries_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "field_libraries"


def create_visual_bloom_field_library(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: str | list[str] | None = None,
    filters: dict[str, object] | None = None,
) -> Path:
    safe = _sanitize_collection(name)
    root = _field_libraries_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe}.json"
    if path.exists():
        raise VisualizerError(f"Field library '{safe}' already exists")
    now = _iso_now()
    doc = {
        "library_name": safe,
        "created_at": now,
        "updated_at": now,
        "title": title or safe,
        "summary": summary or "",
        "tags": normalize_visual_bloom_tags(tags),
        "filters": filters or {},
        "collections": [],
        "artifact_refs": [],
        "generated_artifact_paths": {},
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def list_visual_bloom_field_libraries(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _field_libraries_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in sorted(root.glob("*.json")):
        doc = _safe_load_json(pth)
        if not doc:
            continue
        col_obj = doc.get("collections")
        out.append({
            "library_name": doc.get("library_name", pth.stem),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at", ""),
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "tags": doc.get("tags", []),
            "collection_count": len(col_obj) if isinstance(col_obj, list) else 0,
        })
    out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return out


def load_visual_bloom_field_library(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe = _sanitize_collection(name)
    path = _field_libraries_root(journal_dir) / f"{safe}.json"
    doc = _safe_load_json(path)
    if not doc:
        raise VisualizerError(f"Field library not found or invalid: {name}")
    return doc


def add_visual_bloom_field_library_entry(
    *,
    name: str,
    collection_type: str,
    artifact_ref: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    tags: str | list[str] | None = None,
    sector_family: str | None = None,
) -> Path:
    doc = load_visual_bloom_field_library(name, journal_dir=journal_dir)
    safe = _sanitize_collection(name)
    path = _field_libraries_root(journal_dir) / f"{safe}.json"
    ctype = _sanitize_collection(collection_type)
    allowed = {
        "dossier", "storyboard", "route_compare", "longitudinal", "insight_pack", "atlas_gallery",
        "pathway", "narrative", "constellation", "atlas",
    }
    if ctype not in allowed:
        raise VisualizerError("Unsupported field-library collection type")
    cols_obj = doc.get("collections")
    cols = cols_obj if isinstance(cols_obj, list) else []
    sec_summary = build_visual_bloom_sector_summary(metadata={"tags": normalize_visual_bloom_tags(tags)}, family=sector_family or "HG")
    entry = {
        "collection_id": f"c{len(cols):03d}",
        "collection_type": ctype,
        "title": title or ctype,
        "summary": summary or "",
        "artifact_ref": artifact_ref,
        "notes": notes or "",
        "tags": normalize_visual_bloom_tags(tags),
        "sector_overlay": sec_summary,
        "diagnostics_ref": "",
        "route_context": {},
        "timeline_context": {},
        "dossier_context": {},
    }
    cols.append(entry)
    doc["collections"] = cols
    refs_obj = doc.get("artifact_refs")
    refs = refs_obj if isinstance(refs_obj, list) else []
    refs.append({"type": ctype, "ref": artifact_ref})
    doc["artifact_refs"] = refs
    doc["updated_at"] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def build_visual_bloom_field_library_index(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    index = build_visual_bloom_dossier_candidates(journal_dir=journal_dir)
    for d in list_visual_bloom_dossiers(journal_dir=journal_dir):
        dname = str(d.get("dossier_name", ""))
        if not dname:
            continue
        index.append({
            "artifact_type": "dossier",
            "artifact_ref": str(_dossiers_root(journal_dir) / f"{_sanitize_collection(dname)}.json"),
            "title": d.get("title", dname),
            "tags": d.get("tags", []),
            "created_at": d.get("created_at", ""),
            "dominant_sector": "",
            "sector_family": "",
            "target_mode": "",
            "heat_mode": "",
            "has_bio": True,
            "has_route_compare": True,
            "has_diagnostics": False,
        })
    return index


def filter_visual_bloom_field_library_candidates(
    *,
    candidates: list[dict[str, object]],
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
) -> list[dict[str, object]]:
    return filter_visual_bloom_dossier_candidates(
        candidates=candidates,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
        filter_target=filter_target,
    )


def build_visual_bloom_field_library_summary(*, collections: list[dict[str, object]]) -> dict[str, object]:
    type_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    coverage = {
        "route_compare": 0,
        "longitudinal": 0,
        "dossier": 0,
        "storyboard": 0,
        "diagnostics": 0,
    }
    for col in collections:
        ctype = _sanitize_collection(str(col.get("collection_type", "")))
        if ctype:
            type_counts[ctype] = type_counts.get(ctype, 0) + 1
        so = col.get("sector_overlay")
        sd = so if isinstance(so, dict) else {}
        dom = str(sd.get("dominant_sector", "")).strip().lower().replace(" ", "_")
        if dom:
            sector_counts[dom] = sector_counts.get(dom, 0) + 1
        rc = col.get("route_context")
        rcd = rc if isinstance(rc, dict) else {}
        tgt = _sanitize_collection(str(rcd.get("target_mode", ""))) if rcd.get("target_mode") else ""
        if tgt:
            target_counts[tgt] = target_counts.get(tgt, 0) + 1
        tags_obj = col.get("tags")
        tags = normalize_visual_bloom_tags(tags_obj if isinstance(tags_obj, (str, list)) else None)
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if ctype in coverage:
            coverage[ctype] += 1
        if col.get("diagnostics_ref"):
            coverage["diagnostics"] += 1
    return {
        "summary_version": "v1",
        "collection_count": len(collections),
        "artifact_type_counts": type_counts,
        "dominant_sector_counts": sector_counts,
        "route_target_mode_counts": target_counts,
        "tag_coverage": tag_counts,
        "coverage": coverage,
        "interpretive_note": "Field library summaries are deterministic local curation layers and do not validate physical laws.",
    }


def build_visual_bloom_field_library_model(
    *,
    name: str,
    journal_dir: Path | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
) -> dict[str, object]:
    doc = load_visual_bloom_field_library(name, journal_dir=journal_dir)
    cols_obj = doc.get("collections")
    cols = [c for c in cols_obj if isinstance(c, dict)] if isinstance(cols_obj, list) else []
    index = build_visual_bloom_field_library_index(journal_dir=journal_dir)
    curated = filter_visual_bloom_field_library_candidates(
        candidates=index,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
        filter_target=filter_target,
    )
    filters = {
        "tags": filter_tags or "",
        "sector": filter_sector or "",
        "type": filter_type or "",
        "target": filter_target or "",
    }
    summary = build_visual_bloom_field_library_summary(collections=cols)
    return {
        **doc,
        "filters": filters,
        "collections": cols,
        "field_library_summary": summary,
        "curated_index": curated,
        "generated_at": _iso_now(),
        "experimental": True,
    }


def render_visual_bloom_field_library_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_field_library.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load field-library template: {exc}") from exc
    return template.replace("__PHIOS_FIELD_LIBRARY_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_field_library(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    title: str | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_type: str | None = None,
    filter_target: str | None = None,
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    model = build_visual_bloom_field_library_model(
        name=name,
        journal_dir=journal_dir,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_type=filter_type,
        filter_target=filter_target,
    )
    if title:
        model["title"] = title
    html = render_visual_bloom_field_library_html(model)
    write_bloom_file(html, out / "field_library_index.html")
    (out / "field_library.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    col_dir = out / "collections"
    col_dir.mkdir(parents=True, exist_ok=True)
    cols_obj = model.get("collections")
    cols = cols_obj if isinstance(cols_obj, list) else []
    for idx, col in enumerate(cols):
        if isinstance(col, dict):
            (col_dir / f"collection_{idx:03d}.json").write_text(json.dumps(col, indent=2), encoding="utf-8")
    fls_obj = model.get("field_library_summary")
    fls = fls_obj if isinstance(fls_obj, dict) else {}
    (out / "field_library_summary.json").write_text(json.dumps(fls, indent=2), encoding="utf-8")
    (out / "route_context_summary.json").write_text(json.dumps(fls.get("route_target_mode_counts", {}), indent=2), encoding="utf-8")
    (out / "sector_summary.json").write_text(json.dumps(fls.get("dominant_sector_counts", {}), indent=2), encoding="utf-8")
    (out / "diagnostics_summary.json").write_text(json.dumps(fls.get("coverage", {}), indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="field-library")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")
    included = {
        "index": "field_library_index.html",
        "field_library": "field_library.json",
        "field_library_summary": "field_library_summary.json",
        "sector_summary": "sector_summary.json",
        "diagnostics_summary": "diagnostics_summary.json",
        "route_context_summary": "route_context_summary.json",
        "preview": "preview_image_metadata.json",
    }
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "field_library_version": "v1",
        "type": "visual_bloom_field_library",
        "library_name": model.get("library_name", name),
        "generated_at": model.get("generated_at", _iso_now()),
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase20+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "field_library_manifest.json", payload=manifest)
    return out


def build_visual_bloom_route_timeline(*, model: dict[str, object]) -> dict[str, object]:
    sections_obj = model.get("sections")
    sections = [s for s in sections_obj if isinstance(s, dict)] if isinstance(sections_obj, list) else []
    rows: list[dict[str, object]] = []
    last_type = ""
    for idx, sec in enumerate(sections):
        stype = _sanitize_collection(str(sec.get("section_type", "")))
        if stype not in {"route_compare", "atlas", "branch_replay", "pathway"}:
            continue
        so = sec.get("sector_overlay")
        sd = so if isinstance(so, dict) else {}
        rows.append({
            "index": idx,
            "section_id": sec.get("section_id", f"s{idx:03d}"),
            "section_type": stype,
            "title": sec.get("title", stype),
            "artifact_ref": sec.get("artifact_ref", ""),
            "transition": f"{last_type or 'start'}->{stype}",
            "dominant_sector": sd.get("dominant_sector", ""),
            "sector_family": sd.get("sector_family", ""),
            "note": sec.get("notes", ""),
        })
        last_type = stype
    return {
        "timeline_version": "v1",
        "storyboard_name": model.get("storyboard_name", ""),
        "generated_at": _iso_now(),
        "entries": rows,
        "entry_count": len(rows),
        "status": "experimental_storyboard_route_timeline",
        "interpretive_note": "Timeline summarizes storyboard route/atlas sections as local interpretive context.",
    }


def _safe_load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _scan_manifest_files(*, journal_dir: Path | None, name: str) -> list[Path]:
    root = _journal_root(journal_dir)
    if not root.exists():
        return []
    return sorted(root.rglob(name))


def build_visual_bloom_sector_snapshot(*, entries: list[dict[str, object]]) -> dict[str, object]:
    def _norm(value: object) -> str:
        text = str(value or "").strip().lower().replace(" ", "_")
        return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"})

    family_counts: dict[str, int] = {}
    dominant_counts: dict[str, int] = {}
    for row in entries:
        fam = _norm(row.get("sector_family", ""))
        dom = _norm(row.get("dominant_sector", ""))
        if fam:
            family_counts[fam] = family_counts.get(fam, 0) + 1
        if dom:
            dominant_counts[dom] = dominant_counts.get(dom, 0) + 1
    return {
        "snapshot_version": "v1",
        "entry_count": len(entries),
        "sector_family_counts": family_counts,
        "dominant_sector_counts": dominant_counts,
        "status": "experimental_sector_snapshot",
    }


def build_visual_bloom_sector_comparison_summary(*, entries: list[dict[str, object]]) -> dict[str, object]:
    snap = build_visual_bloom_sector_snapshot(entries=entries)
    dominant = snap.get("dominant_sector_counts")
    dom_rows = dominant.items() if isinstance(dominant, dict) else []
    top = sorted(dom_rows, key=lambda item: item[1], reverse=True)[:3]
    return {
        "comparison_version": "v1",
        "top_dominant_sectors": [{"sector": k, "count": v} for k, v in top],
        "status": "experimental_sector_comparison",
        "interpretive_note": "Sector comparisons are heuristic observatory overlays; they are not physical validation.",
    }


def build_visual_bloom_atlas_gallery_model(
    *,
    journal_dir: Path | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_target: str | None = None,
    filter_heat_mode: str | None = None,
) -> dict[str, object]:
    manifests = _scan_manifest_files(journal_dir=journal_dir, name="route_compare_manifest.json")
    target = _sanitize_collection(filter_target) if filter_target else ""
    if target and target not in {"theoretical", "bio_band", "node"}:
        raise VisualizerError("Invalid atlas target filter. Use theoretical|bio_band|node")
    heat = _sanitize_collection(filter_heat_mode) if filter_heat_mode else ""
    sector = _sanitize_collection(filter_sector) if filter_sector else ""
    tags_req = set(normalize_visual_bloom_tags(filter_tags)) if filter_tags else set()

    entries: list[dict[str, object]] = []
    for manifest_path in manifests:
        manifest = _safe_load_json(manifest_path)
        if not manifest:
            continue
        root = manifest_path.parent
        diff = _safe_load_json(root / "route_diff_summary.json") or {}
        theo = _safe_load_json(root / "theoretical_route.json") or {}
        start_ref = str(manifest.get("start_ref", ""))
        tags = normalize_visual_bloom_tags(str(manifest.get("tags", "")) if isinstance(manifest.get("tags"), str) else None)
        mode = _sanitize_collection(str(manifest.get("heat_mode", "")))
        route_len = int(_to_float(diff.get("theoretical_path_length"), 0.0))
        row = {
            "title": str(manifest.get("title", f"route-compare:{start_ref}")),
            "created_at": str(manifest.get("generated_at", "")),
            "target_mode": "theoretical_vs_bio_band",
            "heat_mode": mode,
            "route_length": route_len,
            "route_cost": _to_float(theo.get("total_cost"), 0.0),
            "dominant_sector": str(diff.get("dominant_sector_theoretical", "")),
            "sector_family": "hg",
            "related_storyboards": [],
            "path": str(root),
            "tags": tags,
            "source": "route_compare",
            "start_ref": start_ref,
        }
        if tags_req and not tags_req.issubset(set(tags)):
            continue
        if heat and mode != heat:
            continue
        if sector and _sanitize_collection(str(row.get("dominant_sector", ""))) != sector:
            continue
        if target and target not in {"theoretical", "bio_band"}:
            continue
        entries.append(row)

    storyboards = list_visual_bloom_storyboards(journal_dir=journal_dir)
    for sb in storyboards:
        sname = str(sb.get("storyboard_name", ""))
        if not sname:
            continue
        try:
            model = build_visual_bloom_storyboard_model(name=sname, journal_dir=journal_dir)
        except VisualizerError:
            continue
        timeline = build_visual_bloom_route_timeline(model=model)
        t_entries_obj = timeline.get("entries")
        t_entries = [e for e in t_entries_obj if isinstance(e, dict)] if isinstance(t_entries_obj, list) else []
        related = [str(e.get("artifact_ref", "")) for e in t_entries]
        if not related:
            continue
        sb_tags_obj = sb.get("tags")
        entries.append({
            "title": str(sb.get("title", sname)),
            "created_at": str(sb.get("created_at", "")),
            "target_mode": "storyboard_timeline",
            "heat_mode": "",
            "route_length": int(_to_float(timeline.get("entry_count"), 0.0)),
            "route_cost": 0.0,
            "dominant_sector": "",
            "sector_family": "",
            "related_storyboards": [sname],
            "path": str(_storyboards_root(journal_dir) / f"{_sanitize_collection(sname)}.json"),
            "tags": normalize_visual_bloom_tags(sb_tags_obj if isinstance(sb_tags_obj, (str, list)) else None),
            "source": "storyboard",
            "start_ref": "",
        })

    entries.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return {
        "gallery_version": "v1",
        "generated_at": _iso_now(),
        "filters": {
            "tags": filter_tags or "",
            "sector": filter_sector or "",
            "target": filter_target or "",
            "heat_mode": filter_heat_mode or "",
        },
        "entries": entries,
        "entry_count": len(entries),
        "sector_snapshot": build_visual_bloom_sector_snapshot(entries=entries),
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }


def render_visual_bloom_atlas_gallery_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_atlas_gallery.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load atlas-gallery template: {exc}") from exc
    return template.replace("__PHIOS_ATLAS_GALLERY_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def filter_visual_bloom_longitudinal_series(
    *,
    series: list[dict[str, object]],
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_target: str | None = None,
) -> list[dict[str, object]]:
    tags_req = set(normalize_visual_bloom_tags(filter_tags)) if filter_tags else set()
    sector = _sanitize_collection(filter_sector) if filter_sector else ""
    target = _sanitize_collection(filter_target) if filter_target else ""
    if target and target not in {"theoretical", "bio_band", "node"}:
        raise VisualizerError("Invalid longitudinal target filter. Use theoretical|bio_band|node")
    out: list[dict[str, object]] = []
    for row in series:
        tags_obj = row.get("tags")
        tags = normalize_visual_bloom_tags(tags_obj if isinstance(tags_obj, (str, list)) else None)
        dom = str(row.get("dominant_sector", "")).strip().lower().replace(" ", "_")
        tgt = str(row.get("target_mode", "")).strip().lower().replace(" ", "_")
        if tags_req and not tags_req.issubset(set(tags)):
            continue
        if sector and dom != sector:
            continue
        if target and target not in tgt:
            continue
        out.append(row)
    return out


def build_visual_bloom_longitudinal_summary(
    *,
    journal_dir: Path | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_target: str | None = None,
) -> dict[str, object]:
    gallery = build_visual_bloom_atlas_gallery_model(journal_dir=journal_dir)
    entries_obj = gallery.get("entries")
    entries = [e for e in entries_obj if isinstance(e, dict)] if isinstance(entries_obj, list) else []
    filtered = filter_visual_bloom_longitudinal_series(
        series=entries,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_target=filter_target,
    )
    target_counts: dict[str, int] = {}
    for row in filtered:
        tgt = str(row.get("target_mode", "unknown")).strip().lower().replace(" ", "_") or "unknown"
        target_counts[tgt] = target_counts.get(tgt, 0) + 1
    return {
        "longitudinal_version": "v1",
        "generated_at": _iso_now(),
        "filters": {
            "tags": filter_tags or "",
            "sector": filter_sector or "",
            "target": filter_target or "",
        },
        "series": filtered,
        "series_count": len(filtered),
        "target_mode_counts": target_counts,
        "sector_snapshot": build_visual_bloom_sector_snapshot(entries=filtered),
        "sector_comparison": build_visual_bloom_sector_comparison_summary(entries=filtered),
        "interpretive_note": "Longitudinal summaries are deterministic local history views, not predictive or truth-bearing science.",
        "experimental": True,
    }


def render_visual_bloom_longitudinal_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_longitudinal.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load longitudinal template: {exc}") from exc
    return template.replace("__PHIOS_LONGITUDINAL_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_longitudinal_summary(
    *,
    output_dir: Path,
    journal_dir: Path | None = None,
    title: str | None = None,
    filter_tags: str | None = None,
    filter_sector: str | None = None,
    filter_target: str | None = None,
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    summary = build_visual_bloom_longitudinal_summary(
        journal_dir=journal_dir,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_target=filter_target,
    )
    if title:
        summary["title"] = title
    html = render_visual_bloom_longitudinal_html(summary)
    write_bloom_file(html, out / "longitudinal_index.html")
    (out / "longitudinal_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "sector_snapshot.json").write_text(json.dumps(summary.get("sector_snapshot", {}), indent=2), encoding="utf-8")
    gallery = build_visual_bloom_atlas_gallery_model(
        journal_dir=journal_dir,
        filter_tags=filter_tags,
        filter_sector=filter_sector,
        filter_target=filter_target,
    )
    (out / "atlas_gallery_summary.json").write_text(json.dumps(gallery, indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="longitudinal")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    included = {
        "index": "longitudinal_index.html",
        "longitudinal_summary": "longitudinal_summary.json",
        "sector_snapshot": "sector_snapshot.json",
        "atlas_gallery_summary": "atlas_gallery_summary.json",
        "preview": "preview_image_metadata.json",
    }
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "longitudinal_version": "v1",
        "type": "visual_bloom_longitudinal",
        "generated_at": summary.get("generated_at", _iso_now()),
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase18+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "longitudinal_manifest.json", payload=manifest)
    return out


def _pathways_root(journal_dir: Path | None = None) -> Path:
    return _journal_root(journal_dir) / "pathways"


def create_visual_bloom_pathway(
    *,
    name: str,
    journal_dir: Path | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    safe_name = _sanitize_collection(name)
    root = _pathways_root(journal_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_name}.json"
    if path.exists():
        raise VisualizerError(f"Pathway already exists: {safe_name}")
    now = _iso_now()
    doc = {
        "pathway_name": safe_name,
        "created_at": now,
        "updated_at": now,
        "title": title or "",
        "summary": summary or "",
        "tags": normalize_visual_bloom_tags(tags),
        "steps": [],
        "branches": [],
        "artifact_paths": {},
        "recommendations": [],
        "bio_context": {
            "phi": PHI,
            "c_star_theoretical": C_STAR_THEORETICAL,
            "c_star_theoretical_formula": "(1 + sqrt(5)) / 4",
            "c_star_theoretical_trig_equiv": C_STAR_THEORETICAL_TRIG_EQUIV,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
            "model_provenance": BIO_MODEL_PROVENANCE,
        },
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def load_visual_bloom_pathway(name: str, *, journal_dir: Path | None = None) -> dict[str, object]:
    safe_name = _sanitize_collection(name)
    path = _pathways_root(journal_dir) / f"{safe_name}.json"
    if not path.exists():
        raise VisualizerError(f"Pathway not found: {safe_name}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise VisualizerError("Pathway document must be an object")
    if not isinstance(doc.get("steps"), list):
        doc["steps"] = []
    if not isinstance(doc.get("tags"), list):
        doc["tags"] = []
    return doc


def list_visual_bloom_pathways(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    root = _pathways_root(journal_dir)
    if not root.exists():
        return []
    out: list[dict[str, object]] = []
    for pth in root.glob("*.json"):
        try:
            doc = json.loads(pth.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        steps = doc.get("steps")
        out.append({
            "pathway_name": doc.get("pathway_name", pth.stem),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at", ""),
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "tags": doc.get("tags", []),
            "step_count": len(steps) if isinstance(steps, list) else 0,
            "branch_count": len(doc.get("branches", [])) if isinstance(doc.get("branches"), list) else 0,
        })
    out.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return out


def add_visual_bloom_pathway_entry(
    *,
    name: str,
    journal_dir: Path | None = None,
    session_ref: str | None = None,
    compare_left: str | None = None,
    compare_right: str | None = None,
    narrative_ref: str | None = None,
    atlas_ref: str | None = None,
    constellation_ref: str | None = None,
    step_title: str | None = None,
    step_note: str | None = None,
    tags: str | list[str] | None = None,
) -> Path:
    doc = load_visual_bloom_pathway(name, journal_dir=journal_dir)
    safe_name = _sanitize_collection(name)
    path = _pathways_root(journal_dir) / f"{safe_name}.json"
    steps = doc.get("steps")
    if not isinstance(steps, list):
        steps = []

    if session_ref:
        step_type = "session"
        ref = {"session_ref": session_ref}
    elif compare_left and compare_right:
        step_type = "compare"
        ref = {"left_ref": compare_left, "right_ref": compare_right}
    elif narrative_ref:
        step_type = "narrative"
        ref = {"narrative_ref": _sanitize_collection(narrative_ref)}
    elif atlas_ref:
        step_type = "atlas"
        ref = {"atlas_ref": atlas_ref}
    elif constellation_ref:
        step_type = "constellation"
        ref = {"constellation_ref": _sanitize_collection(constellation_ref)}
    else:
        raise VisualizerError("Pathway step requires --session, --compare, --narrative, --atlas, or --constellation")

    steps.append({
        "step_id": f"p{len(steps):03d}",
        "step_type": step_type,
        "title": step_title or "",
        "note": step_note or "",
        "tags": normalize_visual_bloom_tags(tags),
        "created_at": _iso_now(),
        "recommended_related": [],
        **ref,
    })
    doc["steps"] = steps
    doc["updated_at"] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def link_visual_bloom_pathway_steps(
    *,
    name: str,
    from_step: str,
    to_step: str,
    journal_dir: Path | None = None,
    branch_label: str | None = None,
    note: str | None = None,
) -> Path:
    doc = load_visual_bloom_pathway(name, journal_dir=journal_dir)
    safe_name = _sanitize_collection(name)
    path = _pathways_root(journal_dir) / f"{safe_name}.json"
    steps = doc.get("steps")
    if not isinstance(steps, list):
        raise VisualizerError("Pathway has no steps")
    ids = {str(s.get("step_id", "")) for s in steps if isinstance(s, dict)}
    if from_step not in ids or to_step not in ids:
        raise VisualizerError("Invalid pathway branch reference")
    branches = doc.get("branches")
    if not isinstance(branches, list):
        branches = []
    branches.append({
        "branch_id": f"b{len(branches):03d}",
        "from_step": from_step,
        "to_step": to_step,
        "label": branch_label or "",
        "note": note or "",
        "created_at": _iso_now(),
    })
    doc["branches"] = branches
    doc["updated_at"] = _iso_now()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def resolve_visual_bloom_pathway_entry(step: dict[str, object], *, journal_dir: Path | None = None) -> dict[str, object]:
    kind = str(step.get("step_type", ""))
    if kind == "session":
        state = load_visual_bloom_state(str(step.get("session_ref", "")), journal_dir=journal_dir)
        return {"step_type": "session", "state": state}
    if kind == "compare":
        left_ref = str(step.get("left_ref", ""))
        right_ref = str(step.get("right_ref", ""))
        if not left_ref or not right_ref:
            raise VisualizerError("Pathway compare step missing refs")
        return {"step_type": "compare", "left_ref": left_ref, "right_ref": right_ref}
    if kind == "narrative":
        n = load_visual_bloom_narrative(str(step.get("narrative_ref", "")), journal_dir=journal_dir)
        return {"step_type": "narrative", "name": n.get("narrative_name", "")}
    if kind == "atlas":
        ref = Path(str(step.get("atlas_ref", "")).strip()).expanduser()
        manifest = ref / "atlas_manifest.json" if ref.is_dir() else ref
        if not manifest.exists():
            raise VisualizerError(f"Atlas reference not found: {ref}")
        return {"step_type": "atlas", "manifest": str(manifest)}
    if kind == "constellation":
        c = load_visual_bloom_constellation(str(step.get("constellation_ref", "")), journal_dir=journal_dir)
        return {"step_type": "constellation", "name": c.get("constellation_name", "")}
    raise VisualizerError(f"Unsupported pathway step type: {kind}")


def extract_visual_bloom_feature_vector(row: dict[str, object]) -> list[float]:
    """Extract lightweight local features for experimental similarity scoring."""
    type_code = {
        "session": 1.0,
        "compare": 2.0,
        "narrative": 3.0,
        "atlas": 4.0,
        "constellation": 5.0,
        "pathway": 6.0,
    }.get(str(row.get("type", "")), 0.0)
    bio_obj = row.get("bio")
    bio = bio_obj if isinstance(bio_obj, dict) else {}
    tags_obj = row.get("tags")
    tag_count = len(tags_obj) if isinstance(tags_obj, list) else 0
    return [
        type_code,
        float(tag_count),
        _to_float(row.get("score"), 0.0),
        _to_float(bio.get("bio_score"), 0.0),
        _to_float(bio.get("bio_distance_from_target"), 1.0),
    ]


def build_visual_bloom_recommendations(
    *,
    target_ref: str,
    journal_dir: Path | None = None,
    top_k: int = 5,
    strategy: str = "golden_angular",
) -> list[dict[str, object]]:
    """Build experimental local similarity suggestions for archived metadata."""
    rows = build_visual_bloom_search_index(journal_dir=journal_dir)
    if not rows:
        return []
    target_idx = next((i for i, r in enumerate(rows) if str(r.get("id", "")) == target_ref), None)
    if target_idx is None:
        return []
    feats = [extract_visual_bloom_feature_vector(r) for r in rows]
    q = [feats[target_idx]]

    strategy_key = _sanitize_collection(strategy) or "golden_angular"
    score_type = "kernel"
    status = "experimental_optional_similarity"

    if strategy_key == "golden_rbf":
        sim = golden_rbf(q, feats, length_scale=1.0)[0]
    elif strategy_key == "golden_angular":
        sim = golden_angular_rbf(q, feats)[0]
    elif strategy_key == "golden_lattice_l1":
        sim = golden_lattice_kernel_l1(q, feats, decay=C_STAR_THEORETICAL)[0]
    elif strategy_key == "adaptive_golden_affinity":
        sim = adaptive_golden_affinity(q, feats)[0]
        score_type = "affinity"
    elif strategy_key == "baseline_rbf":
        # baseline: plain geometric decay without C* prior
        sim = golden_lattice_kernel_l1(q, feats, decay=0.85)[0]
        score_type = "baseline"
        status = "baseline_reference"
    elif strategy_key == "baseline_cosine":
        score_type = "baseline"
        status = "baseline_reference"
        qv = q[0]
        qn = (sum(v * v for v in qv) ** 0.5) or 1e-12
        sim = []
        for x in feats:
            xn = (sum(v * v for v in x) ** 0.5) or 1e-12
            sim.append(sum(a * b for a, b in zip(qv, x)) / (qn * xn))
    else:
        raise VisualizerError(
            "Unknown recommendation strategy '"
            f"{strategy}'. Valid: golden_rbf, golden_angular, golden_lattice_l1, "
            "adaptive_golden_affinity, baseline_rbf, baseline_cosine"
        )

    out: list[dict[str, object]] = []
    for i, score in enumerate(sim):
        if i == target_idx:
            continue
        out.append({
            "id": rows[i].get("id", ""),
            "type": rows[i].get("type", ""),
            "title": rows[i].get("title", ""),
            "similarity": float(score),
            "recommendation_status": "experimental_local_similarity",
            "strategy": strategy_key,
            "strategy_status": status,
            "score_type": score_type,
            "experimental": strategy_key.startswith("golden") or strategy_key == "adaptive_golden_affinity",
            "feature_vector_version": "v2",
        })
    out.sort(key=lambda r: _to_float(r.get("similarity"), 0.0), reverse=True)
    return out[: max(1, top_k)]


def benchmark_visual_bloom_recommendations(
    *,
    journal_dir: Path | None = None,
    strategies: list[str] | None = None,
    top_k: int = 5,
    max_targets: int = 10,
) -> dict[str, object]:
    rows = build_visual_bloom_search_index(journal_dir=journal_dir)
    target_refs = [str(r.get("id", "")) for r in rows if str(r.get("id", ""))][: max(1, max_targets)]
    selected = strategies or [
        "golden_rbf",
        "golden_angular",
        "golden_lattice_l1",
        "adaptive_golden_affinity",
        "baseline_rbf",
        "baseline_cosine",
    ]

    def _recommender(target: str, strat: str, k: int) -> list[dict[str, object]]:
        return build_visual_bloom_recommendations(
            target_ref=target,
            journal_dir=journal_dir,
            top_k=k,
            strategy=strat,
        )

    return benchmark_recommendation_strategies(
        target_refs=target_refs,
        strategies=selected,
        recommender=_recommender,
        top_k=top_k,
    )


def build_visual_bloom_search_index(*, journal_dir: Path | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for s in list_visual_bloom_sessions(journal_dir=journal_dir):
        rows.append({"type": "session", "id": str(s.get("session_id", "")), "title": str(s.get("label", "")), "tags": s.get("tags", []), "collection": str(s.get("collection", "")), "mode": str(s.get("mode", "")), "preset": str(s.get("preset", "")), "lens": str(s.get("lens", "")), "audio": str(s.get("audio", "")), "bio": s.get("bio", {})})
    for c in list_visual_bloom_compare_sets(journal_dir=journal_dir):
        rows.append({"type": "compare", "id": str(c.get("name", "")), "title": str(c.get("label", "")), "tags": c.get("tags", []), "bio": {}})
    for n in list_visual_bloom_narratives(journal_dir=journal_dir):
        rows.append({"type": "narrative", "id": str(n.get("narrative_name", "")), "title": str(n.get("title", "")), "tags": n.get("tags", []), "bio": {"bio_status": BIO_VACUUM_STATUS}})
    for c in list_visual_bloom_constellations(journal_dir=journal_dir):
        rows.append({"type": "constellation", "id": str(c.get("constellation_name", "")), "title": str(c.get("title", "")), "tags": c.get("tags", []), "bio": {}})
    for p in list_visual_bloom_pathways(journal_dir=journal_dir):
        rows.append({"type": "pathway", "id": str(p.get("pathway_name", "")), "title": str(p.get("title", "")), "tags": p.get("tags", []), "bio": {"bio_status": BIO_VACUUM_STATUS}})

    atlas_root = _journal_root(journal_dir)
    for manifest in atlas_root.rglob("atlas_manifest.json") if atlas_root.exists() else []:
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        rows.append({
            "type": "atlas",
            "id": str(doc.get("narrative_name", manifest.parent.name)),
            "title": str(doc.get("narrative_name", "")),
            "tags": doc.get("tags", []),
            "bio": {"bio_status": BIO_VACUUM_STATUS},
        })
    return rows


def search_visual_bloom_metadata(
    *,
    query: str,
    journal_dir: Path | None = None,
    search_tags: str | None = None,
    search_type: str | None = None,
    search_bio: str | None = None,
) -> list[dict[str, object]]:
    tokens = [t for t in query.lower().split() if t]
    must_tags = set(normalize_visual_bloom_tags(search_tags)) if search_tags else set()
    type_filter = _sanitize_collection(search_type) if search_type else ""
    bio_filter = (search_bio or "").strip().lower()

    results: list[dict[str, object]] = []
    for row in build_visual_bloom_search_index(journal_dir=journal_dir):
        rtype = str(row.get("type", "")).lower()
        if type_filter and rtype != type_filter:
            continue
        tags_obj = row.get("tags")
        row_tags = {str(t) for t in tags_obj if str(t)} if isinstance(tags_obj, list) else set()
        if must_tags and not must_tags.issubset(row_tags):
            continue

        bio_obj = row.get("bio")
        bio = bio_obj if isinstance(bio_obj, dict) else {}
        if bio_filter == "experimental" and str(bio.get("bio_status", "")).lower() != "experimental":
            continue
        if bio_filter == "available" and not bio:
            continue
        if bio_filter == "near-target":
            dist = _to_float(bio.get("bio_distance_from_target"), 999.0)
            if dist > 0.003:
                continue

        blob = " ".join([
            str(row.get("id", "")),
            str(row.get("title", "")),
            " ".join(sorted(row_tags)),
            str(row.get("collection", "")),
            str(row.get("mode", "")),
            str(row.get("preset", "")),
            str(row.get("lens", "")),
            str(row.get("audio", "")),
            str(bio.get("bio_status", "")),
        ]).lower()
        if tokens and not all(tok in blob for tok in tokens):
            continue
        score = sum(1 for tok in tokens if tok in blob) + (2 if must_tags else 0)
        results.append({**row, "score": score})

    results.sort(key=lambda r: (int(_to_float(r.get("score"), 0.0)), str(r.get("id", ""))), reverse=True)
    return results


def build_visual_bloom_sector_summary(*, metadata: dict[str, object] | None = None, family: str = "HG") -> dict[str, object]:
    md = metadata or {}
    weights = infer_visual_bloom_sector_weights(md)
    sectors = list_visual_bloom_sectors(family)
    return {
        "sector_family": family,
        "dominant_sector": dominant_sector(weights),
        "sector_weights": weights,
        "available_sectors": sectors,
        "status": "experimental_symbolic_ontology",
    }


def build_visual_bloom_dashboard_model(*, journal_dir: Path | None = None, search: str | None = None) -> dict[str, object]:
    sessions = list_visual_bloom_sessions(journal_dir=journal_dir)[:12]
    compares = list_visual_bloom_compare_sets(journal_dir=journal_dir)[:12]
    pathways = list_visual_bloom_pathways(journal_dir=journal_dir)[:12]
    constellations = list_visual_bloom_constellations(journal_dir=journal_dir)[:12]
    rows = search_visual_bloom_metadata(query=search or "", journal_dir=journal_dir) if search else []
    first_session = sessions[0] if sessions else {}
    sector_summary = build_visual_bloom_sector_summary(metadata=first_session if isinstance(first_session, dict) else {}, family="HG")
    top_ref = str(sessions[0].get("session_id", "")) if sessions else ""
    recommendations = build_visual_bloom_recommendations(target_ref=top_ref, journal_dir=journal_dir, strategy="golden_angular") if top_ref else []
    diagnostics_snapshot = build_visual_bloom_strategy_diagnostics(target_ref=top_ref, journal_dir=journal_dir) if top_ref else {}
    atlas_gallery = build_visual_bloom_atlas_gallery_model(journal_dir=journal_dir)
    longitudinal = build_visual_bloom_longitudinal_summary(journal_dir=journal_dir)
    entries_obj = atlas_gallery.get("entries")
    gallery_entries = [e for e in entries_obj if isinstance(e, dict)] if isinstance(entries_obj, list) else []
    recent_route_compares = [e for e in gallery_entries if str(e.get("source", "")) == "route_compare"][:10]
    storyboards = list_visual_bloom_storyboards(journal_dir=journal_dir)[:10]
    dossiers = list_visual_bloom_dossiers(journal_dir=journal_dir)[:10]
    field_libraries = list_visual_bloom_field_libraries(journal_dir=journal_dir)[:10]
    timeline_entries: list[dict[str, object]] = []
    for row in storyboards[:3]:
        sname = str(row.get("storyboard_name", ""))
        if not sname:
            continue
        try:
            s_model = build_visual_bloom_storyboard_model(name=sname, journal_dir=journal_dir)
        except VisualizerError:
            continue
        timeline_entries.append({
            "storyboard_name": sname,
            "timeline": build_visual_bloom_route_timeline(model=s_model),
        })
    return {
        "generated_at": _iso_now(),
        "search": search or "",
        "sessions": sessions,
        "compares": compares,
        "pathways": pathways,
        "constellations": constellations,
        "results": rows,
        "recommendations": recommendations,
        "diagnostics_snapshot": diagnostics_snapshot,
        "recent_route_compares": recent_route_compares,
        "recent_storyboards": storyboards,
        "recent_dossiers": dossiers,
        "recent_field_libraries": field_libraries,
        "recent_atlas_gallery_entries": gallery_entries[:10],
        "longitudinal_snapshot": {
            "series_count": longitudinal.get("series_count", 0),
            "target_mode_counts": longitudinal.get("target_mode_counts", {}),
            "sector_snapshot": longitudinal.get("sector_snapshot", {}),
        },
        "storyboard_timelines": timeline_entries,
        "route_target_mode_counts": longitudinal.get("target_mode_counts", {}),
        "dossier_summary_counts": {
            "dossier_count": len(dossiers),
            "section_count": sum(int(_to_float(d.get("section_count"), 0.0)) for d in dossiers),
        },
        "field_library_summary_counts": {
            "library_count": len(field_libraries),
            "collection_count": sum(int(_to_float(d.get("collection_count"), 0.0)) for d in field_libraries),
        },
        "sector_summary": sector_summary,
        "bio_banner": {
            "phi": PHI,
            "c_star_theoretical": C_STAR_THEORETICAL,
            "c_star_theoretical_formula": "(1 + sqrt(5)) / 4",
            "c_star_theoretical_trig_equiv": C_STAR_THEORETICAL_TRIG_EQUIV,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
            "model_provenance": BIO_MODEL_PROVENANCE,
        },
    }


def render_visual_bloom_dashboard_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_dashboard.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load dashboard template: {exc}") from exc
    return template.replace("__PHIOS_DASHBOARD_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def launch_visual_bloom_dashboard(*, output_path: Path | None = None, open_browser: bool = True, journal_dir: Path | None = None, search: str | None = None) -> Path:
    model = build_visual_bloom_dashboard_model(journal_dir=journal_dir, search=search)
    html = render_visual_bloom_dashboard_html(model)
    target = output_path or Path("/tmp/phios_bloom_dashboard.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written


def render_visual_bloom_pathway_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_pathway.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load pathway template: {exc}") from exc
    return template.replace("__PHIOS_PATHWAY_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_pathway(
    *,
    name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    with_integrity: bool = False,
    tags: str | list[str] | None = None,
) -> Path:
    pathway = load_visual_bloom_pathway(name, journal_dir=journal_dir)
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    steps_dir = out / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)

    raw_steps = pathway.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    rendered: list[dict[str, object]] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        resolved = resolve_visual_bloom_pathway_entry(step, journal_dir=journal_dir)
        step_json = steps_dir / f"step_{idx:03d}.json"
        payload = {"index": idx, "step": step, "resolved": resolved}
        step_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        step_ref = str(step.get("session_ref", step.get("narrative_ref", step.get("constellation_ref", step.get("atlas_ref", "")))))
        rendered.append({
            "index": idx,
            "step_type": step.get("step_type", ""),
            "step_id": step.get("step_id", ""),
            "title": step.get("title", ""),
            "note": step.get("note", ""),
            "tags": step.get("tags", []),
            "json": str(Path("steps") / step_json.name),
            "resolved": resolved,
            "experimental_recommendations": build_visual_bloom_recommendations(target_ref=step_ref, journal_dir=journal_dir, strategy="golden_angular") if step_ref else [],
        })

    recommendations = build_visual_bloom_recommendations(target_ref=str(pathway.get("pathway_name", name)), journal_dir=journal_dir, strategy="golden_angular")
    diagnostics_snapshot = build_visual_bloom_strategy_diagnostics(target_ref=str(pathway.get("pathway_name", name)), journal_dir=journal_dir)
    sector_summary = build_visual_bloom_sector_summary(metadata=pathway if isinstance(pathway, dict) else {}, family="HG")
    branches_obj = pathway.get("branches")
    branches = branches_obj if isinstance(branches_obj, list) else []
    outgoing_by_step: dict[str, list[dict[str, object]]] = {}
    for b in branches:
        if not isinstance(b, dict):
            continue
        key = str(b.get("from_step", ""))
        outgoing_by_step.setdefault(key, []).append({
            "to_step": str(b.get("to_step", "")),
            "label": str(b.get("label", "")),
            "note": str(b.get("note", "")),
        })

    model = {
        "pathway_name": pathway.get("pathway_name", _sanitize_collection(name)),
        "title": pathway.get("title", ""),
        "summary": pathway.get("summary", ""),
        "tags": normalize_visual_bloom_tags(tags) or pathway.get("tags", []),
        "created_at": pathway.get("created_at", ""),
        "updated_at": pathway.get("updated_at", ""),
        "exported_at": _iso_now(),
        "step_count": len(rendered),
        "steps": rendered,
        "branches": branches,
        "branch_outgoing": outgoing_by_step,
        "recommendations": recommendations,
        "diagnostics_snapshot": diagnostics_snapshot,
        "recent_route_compares": [],
        "recent_storyboards": list_visual_bloom_storyboards(journal_dir=journal_dir)[:10],
        "sector_summary": sector_summary,
        "bio_context": pathway.get("bio_context", attach_visual_bloom_bio_metadata({}).get("bio", {})),
    }
    html = render_visual_bloom_pathway_html(model)
    write_bloom_file(html, out / "journey_index.html")
    (out / "pathway.json").write_text(json.dumps(pathway, indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="pathway")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    included = {"index": "journey_index.html", "pathway": "pathway.json", "preview": "preview_image_metadata.json"}
    for row in rendered:
        included[f"step_{row['index']}"] = str(row.get("json", ""))
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "pathway_version": "v1",
        "manifest_version": "v1",
        "pathway_type": "visual_bloom_field_journey",
        "pathway_name": model["pathway_name"],
        "bundle_created_at": model["exported_at"],
        "step_count": len(rendered),
        "tags": model["tags"],
        "bio_context": model["bio_context"],
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "preview": preview,
        "compatibility_version": "phase12+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "pathway_manifest.json", payload=manifest)
    return out



def build_visual_bloom_insight_pack_model(
    *,
    pathway_name: str,
    journal_dir: Path | None = None,
    include_atlas: bool = False,
    insight_pack_heat_mode: str = "target_proximity",
    title: str | None = None,
) -> dict[str, object]:
    pathway = load_visual_bloom_pathway(pathway_name, journal_dir=journal_dir)
    sector_summary = build_visual_bloom_sector_summary(metadata=pathway if isinstance(pathway, dict) else {}, family="HG")
    recommendations = build_visual_bloom_recommendations(target_ref=str(pathway.get("pathway_name", pathway_name)), journal_dir=journal_dir, strategy="golden_angular")
    diagnostics_snapshot = build_visual_bloom_strategy_diagnostics(target_ref=str(pathway.get("pathway_name", pathway_name)), journal_dir=journal_dir)
    atlas_summary: dict[str, object] = {}
    if include_atlas:
        atlas_model = build_visual_bloom_atlas_model(atlas_target="theoretical", atlas_heat_mode=insight_pack_heat_mode, journal_dir=journal_dir)
        atlas_summary = {
            "target_mode": atlas_model.get("target_mode", ""),
            "route_length": atlas_model.get("route_length", 0),
            "route_cost": atlas_model.get("route_cost", 0.0),
            "heat_mode": atlas_model.get("heat_mode", insight_pack_heat_mode),
            "heat_summary": atlas_model.get("heat_summary", {}),
            "dominant_sector": atlas_model.get("dominant_sector", ""),
        }
    return {
        "insight_pack_version": "v1",
        "generated_at": _iso_now(),
        "title": title or str(pathway.get("title", pathway_name)),
        "pathway": pathway,
        "sector_summary": sector_summary,
        "recommendations": recommendations,
        "diagnostics_snapshot": diagnostics_snapshot,
        "recent_route_compares": [],
        "recent_storyboards": list_visual_bloom_storyboards(journal_dir=journal_dir)[:10],
        "atlas_summary": atlas_summary,
        "bio_framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }


def render_visual_bloom_insight_pack_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_insight_pack.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load insight-pack template: {exc}") from exc
    return template.replace("__PHIOS_INSIGHT_PACK_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_insight_pack(
    *,
    pathway_name: str,
    output_dir: Path,
    journal_dir: Path | None = None,
    title: str | None = None,
    include_atlas: bool = False,
    heat_mode: str = "target_proximity",
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    model = build_visual_bloom_insight_pack_model(
        pathway_name=pathway_name,
        journal_dir=journal_dir,
        include_atlas=include_atlas,
        insight_pack_heat_mode=heat_mode,
        title=title,
    )
    html = render_visual_bloom_insight_pack_html(model)
    write_bloom_file(html, out / "insight_pack_index.html")
    (out / "pathway.json").write_text(json.dumps(model.get("pathway", {}), indent=2), encoding="utf-8")
    (out / "sector_summary.json").write_text(json.dumps(model.get("sector_summary", {}), indent=2), encoding="utf-8")
    (out / "recommendations.json").write_text(json.dumps(model.get("recommendations", []), indent=2), encoding="utf-8")
    if include_atlas:
        (out / "atlas_summary.json").write_text(json.dumps(model.get("atlas_summary", {}), indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="insight-pack")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    included = {
        "index": "insight_pack_index.html",
        "pathway": "pathway.json",
        "sector_summary": "sector_summary.json",
        "recommendations": "recommendations.json",
        "preview": "preview_image_metadata.json",
    }
    if include_atlas:
        included["atlas_summary"] = "atlas_summary.json"
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "insight_pack_version": "v1",
        "type": "visual_bloom_insight_pack",
        "pathway_name": pathway_name,
        "generated_at": model.get("generated_at", _iso_now()),
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase15+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "insight_pack_manifest.json", payload=manifest)
    return out


def build_visual_bloom_branch_replay_model(*, pathway_name: str, journal_dir: Path | None = None) -> dict[str, object]:
    pathway = load_visual_bloom_pathway(pathway_name, journal_dir=journal_dir)
    raw_steps = pathway.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    raw_branches = pathway.get("branches")
    branches = raw_branches if isinstance(raw_branches, list) else []

    outgoing: dict[str, list[dict[str, object]]] = {}
    for b in branches:
        if not isinstance(b, dict):
            continue
        from_step = str(b.get("from_step", ""))
        outgoing.setdefault(from_step, []).append({
            "to_step": str(b.get("to_step", "")),
            "label": str(b.get("label", "")),
            "note": str(b.get("note", "")),
        })

    enriched_steps: list[dict[str, object]] = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        sid = str(step.get("step_id", f"p{idx:03d}"))
        sref = str(step.get("session_ref", step.get("narrative_ref", step.get("constellation_ref", step.get("atlas_ref", "")))))
        recs = build_visual_bloom_recommendations(target_ref=sref, journal_dir=journal_dir, strategy="golden_angular") if sref else []
        enriched_steps.append({
            "index": idx,
            "step_id": sid,
            "step_type": str(step.get("step_type", "")),
            "title": str(step.get("title", "")),
            "note": str(step.get("note", "")),
            "tags": step.get("tags", []),
            "outgoing_branches": outgoing.get(sid, []),
            "recommended_next": recs[:3],
            "sector_overlay": build_visual_bloom_sector_summary(metadata=step, family="HG"),
        })

    return {
        "generated_at": _iso_now(),
        "pathway_name": pathway.get("pathway_name", pathway_name),
        "title": pathway.get("title", ""),
        "summary": pathway.get("summary", ""),
        "step_count": len(enriched_steps),
        "branch_count": len(branches),
        "steps": enriched_steps,
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }


def render_visual_bloom_branch_replay_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_branch_replay.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load branch replay template: {exc}") from exc
    return template.replace("__PHIOS_BRANCH_REPLAY_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def launch_visual_bloom_branch_replay(*, pathway_name: str, output_path: Path | None = None, open_browser: bool = True, journal_dir: Path | None = None) -> Path:
    model = build_visual_bloom_branch_replay_model(pathway_name=pathway_name, journal_dir=journal_dir)
    html = render_visual_bloom_branch_replay_html(model)
    target = output_path or Path("/tmp/phios_bloom_branch_replay.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written


def _route_overlap_ratio(a: list[int], b: list[int]) -> float:
    sa, sb = set(a), set(b)
    u = len(sa | sb)
    return (len(sa & sb) / u) if u else 1.0


def _route_divergence_index(a: list[int], b: list[int]) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def build_visual_bloom_strategy_diagnostics(*, target_ref: str, journal_dir: Path | None = None, top_k: int = 5) -> dict[str, object]:
    strategies = ["golden_rbf", "golden_angular", "golden_lattice_l1", "adaptive_golden_affinity", "baseline_rbf", "baseline_cosine"]
    rows: dict[str, list[dict[str, object]]] = {}
    for sname in strategies:
        rows[sname] = build_visual_bloom_recommendations(target_ref=target_ref, journal_dir=journal_dir, top_k=top_k, strategy=sname)

    ids = {k: {str(r.get("id", "")) for r in v if str(r.get("id", ""))} for k, v in rows.items()}
    overlap: dict[str, float] = {}
    keys = list(ids.keys())
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ua, ub = ids[a], ids[b]
            overlap[f"{a}__vs__{b}"] = (len(ua & ub) / len(ua | ub)) if (ua | ub) else 1.0

    return {
        "target_ref": target_ref,
        "top_k": top_k,
        "strategies": rows,
        "overlap": overlap,
        "status": "experimental_strategy_diagnostics",
    }


def build_visual_bloom_route_compare_model(
    *,
    start_ref: str,
    route_compare_title: str | None = None,
    route_compare_heat_mode: str = "target_proximity",
    include_sector_overlays: bool = False,
    journal_dir: Path | None = None,
) -> dict[str, object]:
    nodes = [list(n) for n in build_lattice_4d_nodes()]
    graph = build_golden_atlas_graph(nodes, max_l1_radius=1, max_neighbors=16)

    state = load_visual_bloom_state(start_ref, journal_dir=journal_dir)
    point = [
        _to_float(state.get("coherenceC"), C_STAR_THEORETICAL),
        _to_float(state.get("frequency"), 7.83) / 40.0,
        _to_float(state.get("particleCount"), 1500.0) / 2500.0,
        _to_float(state.get("noiseScale"), 0.005) / 0.02,
    ]
    start_idx = nearest_lattice_node(nodes, point)

    theoretical_idx = nearest_lattice_node(nodes, [C_STAR_THEORETICAL] * 4)
    theoretical_route = find_path_to_target(nodes, graph, start_idx=start_idx, target_idx=theoretical_idx, target_point=[C_STAR_THEORETICAL] * 4)
    bio_route = find_path_to_bio_band(nodes, graph, start_idx=start_idx)

    tr_obj = theoretical_route.get("path")
    br_obj = bio_route.get("path")
    tr_seq = tr_obj if isinstance(tr_obj, list) else []
    br_seq = br_obj if isinstance(br_obj, list) else []
    tr_path = [i for i in tr_seq if isinstance(i, int)]
    br_path = [i for i in br_seq if isinstance(i, int)]

    end_a = tr_path[-1] if tr_path else -1
    end_b = br_path[-1] if br_path else -1
    end_dist = _to_float(abs(end_a - end_b), 0.0) if end_a >= 0 and end_b >= 0 else 0.0

    heat_a = compute_atlas_heat(nodes, graph, target_point=[C_STAR_THEORETICAL] * 4, mode=route_compare_heat_mode)
    heat_b = compute_atlas_heat(nodes, graph, target_point=[BIO_VACUUM_TARGET] * 4, mode=route_compare_heat_mode)

    sector_overlay: dict[str, object] = {}
    if include_sector_overlays:
        sec_a = build_visual_bloom_sector_summary(metadata={"coherenceC": C_STAR_THEORETICAL, "noiseScale": 0.003}, family="HG")
        sec_b = build_visual_bloom_sector_summary(metadata={"coherenceC": BIO_VACUUM_TARGET, "noiseScale": 0.006}, family="HG")
        sector_overlay = {"theoretical": sec_a, "bio_band": sec_b}

    theo_obj = sector_overlay.get("theoretical")
    bio_obj = sector_overlay.get("bio_band")
    theo_sec = theo_obj if isinstance(theo_obj, dict) else {}
    bio_sec = bio_obj if isinstance(bio_obj, dict) else {}

    diff = {
        "path_length_theoretical": len(tr_path),
        "path_length_bio_band": len(br_path),
        "total_cost_theoretical": _to_float(theoretical_route.get("cost"), 0.0),
        "total_cost_bio_band": _to_float(bio_route.get("cost"), 0.0),
        "overlap_ratio": _route_overlap_ratio(tr_path, br_path),
        "divergence_step_index": _route_divergence_index(tr_path, br_path),
        "end_node_distance": end_dist,
        "heat_avg_delta": ((sum(heat_a) / len(heat_a)) - (sum(heat_b) / len(heat_b))) if heat_a and heat_b else 0.0,
        "dominant_sector_theoretical": str(theo_sec.get("dominant_sector", "")),
        "dominant_sector_bio_band": str(bio_sec.get("dominant_sector", "")),
    }

    diagnostics = build_visual_bloom_strategy_diagnostics(target_ref=start_ref, journal_dir=journal_dir)

    return {
        "route_compare_version": "v1",
        "generated_at": _iso_now(),
        "title": route_compare_title or f"Route compare · {start_ref}",
        "start_ref": start_ref,
        "start_idx": start_idx,
        "heat_mode": route_compare_heat_mode,
        "theoretical_route": theoretical_route,
        "bio_band_route": bio_route,
        "route_diff_summary": diff,
        "sector_overlay_summary": sector_overlay,
        "strategy_diagnostics": diagnostics,
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_target": BIO_VACUUM_TARGET,
            "bio_band_low": BIO_VACUUM_BAND_LOW,
            "bio_band_high": BIO_VACUUM_BAND_HIGH,
            "bio_status": BIO_VACUUM_STATUS,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }


def render_visual_bloom_route_compare_html(model: dict[str, object]) -> str:
    try:
        template = resources.files("phios.templates").joinpath("sonic_route_compare.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load route-compare template: {exc}") from exc
    return template.replace("__PHIOS_ROUTE_COMPARE_MODEL_JSON__", json.dumps(model, separators=(",", ":")))


def export_visual_bloom_route_compare_bundle(
    *,
    start_ref: str,
    output_dir: Path,
    route_compare_title: str | None = None,
    route_compare_heat_mode: str = "target_proximity",
    include_sector_overlays: bool = False,
    journal_dir: Path | None = None,
    with_integrity: bool = False,
) -> Path:
    out = output_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    model = build_visual_bloom_route_compare_model(
        start_ref=start_ref,
        route_compare_title=route_compare_title,
        route_compare_heat_mode=route_compare_heat_mode,
        include_sector_overlays=include_sector_overlays,
        journal_dir=journal_dir,
    )
    html = render_visual_bloom_route_compare_html(model)
    write_bloom_file(html, out / "route_compare_index.html")
    (out / "theoretical_route.json").write_text(json.dumps(model.get("theoretical_route", {}), indent=2), encoding="utf-8")
    (out / "bio_band_route.json").write_text(json.dumps(model.get("bio_band_route", {}), indent=2), encoding="utf-8")
    (out / "route_diff_summary.json").write_text(json.dumps(model.get("route_diff_summary", {}), indent=2), encoding="utf-8")
    (out / "strategy_diagnostics.json").write_text(json.dumps(model.get("strategy_diagnostics", {}), indent=2), encoding="utf-8")
    if include_sector_overlays:
        (out / "sector_overlay_summary.json").write_text(json.dumps(model.get("sector_overlay_summary", {}), indent=2), encoding="utf-8")
    preview = augment_visual_bloom_preview_metadata(source="route-compare")
    (out / "preview_image_metadata.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    included = {
        "index": "route_compare_index.html",
        "theoretical_route": "theoretical_route.json",
        "bio_band_route": "bio_band_route.json",
        "route_diff_summary": "route_diff_summary.json",
        "strategy_diagnostics": "strategy_diagnostics.json",
        "preview": "preview_image_metadata.json",
    }
    if include_sector_overlays:
        included["sector_overlay_summary"] = "sector_overlay_summary.json"
    hashes = compute_visual_bloom_bundle_hashes(out, included)
    manifest = {
        "manifest_version": "v1",
        "route_compare_version": "v1",
        "type": "visual_bloom_route_compare",
        "start_ref": start_ref,
        "generated_at": model.get("generated_at", _iso_now()),
        "heat_mode": route_compare_heat_mode,
        "included_files": included,
        "integrity_mode": "sha256" if with_integrity else "none",
        "file_hashes_sha256": hashes if with_integrity else {},
        "experimental": True,
        "compatibility_version": "phase16+",
        "compatibility_notes": "Additive schema; older artifacts remain supported with safe defaults.",
    }
    write_visual_bloom_bundle_manifest(manifest_path=out / "route_compare_manifest.json", payload=manifest)
    return out


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


def render_compare_bloom_html(left_params: dict[str, object], right_params: dict[str, object], diff_metrics: dict[str, object]) -> str:
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
    html = html.replace("__PHIOS_COMPARE_DIFF_JSON__", json.dumps(diff_metrics, separators=(",", ":")))
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
    tags: str | list[str] | None = None,
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
    tags: str | list[str] | None = None,
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
    state_idx: int | None = None,
    step: int = 0,
) -> Path:
    session, _, latest_idx = resolve_visual_bloom_state_ref(session_ref, journal_dir=journal_dir)
    if step != 0:
        state, selected_idx, total = step_visual_bloom_state(session, latest_idx if state_idx is None else state_idx, step)
    else:
        state, selected_idx, total = select_visual_bloom_state(session, state_idx=state_idx)

    effective_preset: str | None = preset or str(state.get("preset", session.get("preset", "none")))
    effective_lens: str | None = lens or str(state.get("lens", session.get("lens", "none")))
    if effective_preset == "none":
        effective_preset = None
    if effective_lens == "none":
        effective_lens = None

    replay_base = _compose_visual_params(dict(state), preset=effective_preset, lens=effective_lens, audio_reactive=audio_reactive)
    params = _with_live_contract(
        replay_base,
        mode="replay",
        session_id=str(session.get("session_id", "replay")),
        session_label=str(session.get("label", "")) or None,
        state_timestamp=str(state.get("stateTimestamp", _iso_now())),
        preset=effective_preset,
        lens=effective_lens,
        audio_requested=audio_reactive,
        collection=str(session.get("collection", "")) or None,
    )
    params["sourceLabel"] = "PhiOS Visual Bloom · Replay"
    params["stateIndex"] = selected_idx
    params["stateTotal"] = total
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
    export_report_path: Path | None = None,
) -> Path:
    left_session, left_state, left_idx = resolve_visual_bloom_state_ref(left_ref, journal_dir=journal_dir)
    right_session, right_state, right_idx = resolve_visual_bloom_state_ref(right_ref, journal_dir=journal_dir)

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
    left_params["stateIndex"] = left_idx
    left_states = left_session.get("states")
    left_total = len(left_states) if isinstance(left_states, list) else 1
    left_params["stateTotal"] = left_total

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
    right_params["stateIndex"] = right_idx
    right_states = right_session.get("states")
    right_total = len(right_states) if isinstance(right_states, list) else 1
    right_params["stateTotal"] = right_total

    diff_metrics = compute_visual_bloom_diff_metrics(left_params, right_params)
    if export_report_path is not None:
        export_visual_bloom_compare_report(output_path=export_report_path, left=left_params, right=right_params, diff=diff_metrics)
    html = render_compare_bloom_html(left_params, right_params, diff_metrics)
    target = output_path or Path("/tmp/phios_bloom_compare.html")
    written = write_bloom_file(html, target)
    _open_browser(written, open_browser)
    return written
