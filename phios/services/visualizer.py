"""Local Visual Bloom adapter for PhiOS.

This module reads live PhiKernel field_state and renders a local bloom HTML.
It is a local-first adapter layer: PhiKernel remains runtime source-of-truth.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
import importlib.resources as resources


class VisualizerError(RuntimeError):
    """Raised when visualizer field_state or rendering fails."""


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


def _with_live_contract(params: dict[str, object], *, mode: str, refresh_seconds: float | None = None) -> dict[str, object]:
    """Build the stable JSON contract shared with the browser live poller."""
    payload: dict[str, object] = {
        **params,
        "mode": mode,
        "timestamp": int(time.time()),
    }
    if refresh_seconds is not None:
        payload["refreshSeconds"] = round(max(refresh_seconds, 0.2), 2)
    return payload


def render_bloom_html(
    params: dict[str, object],
    *,
    live_mode: bool = False,
    refresh_seconds: float = 2.0,
    params_path: str = "",
) -> str:
    """Render bloom HTML by injecting params and live placeholders into template."""
    try:
        template = resources.files("phios.templates").joinpath("sonic_emergence.html").read_text(encoding="utf-8")
    except Exception as exc:
        raise VisualizerError(f"Unable to load visual template: {exc}") from exc

    initial_marker = "__PHIOS_INITIAL_PARAMS_JSON__"
    if initial_marker not in template:
        raise VisualizerError("Template marker __PHIOS_INITIAL_PARAMS_JSON__ not found.")
    html = template.replace(initial_marker, json.dumps(params, separators=(",", ":")))

    html = html.replace("__PHIOS_LIVE_ENABLED__", "true" if live_mode else "false")
    html = html.replace("__PHIOS_REFRESH_MS__", str(int(max(refresh_seconds, 0.2) * 1000)))
    html = html.replace("__PHIOS_REFRESH_SECONDS__", f"{max(refresh_seconds, 0.2):.2f}")
    html = html.replace("__PHIOS_PARAMS_PATH__", params_path)
    return html


def write_bloom_file(html: str, output_path: Path) -> Path:
    """Write HTML artifact to local path; fallback to temp file if needed."""
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
    """Persist current mapped params for live-loop updates consumed by browser polling."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(params, indent=2), encoding="utf-8")
    return output_path


def launch_bloom(output_path: Path | None = None, open_browser: bool = True) -> Path:
    """Generate a snapshot bloom from live kernel field_state and optionally open it."""
    field_data, status_data = poll_kernel_state()
    mapped = map_kernel_to_visual_params(field_data, status_data)
    params = _with_live_contract(mapped, mode="snapshot")
    html = render_bloom_html(params, live_mode=False)

    target = output_path or Path("/tmp/phios_bloom.html")
    written = write_bloom_file(html, target)

    if open_browser:
        try:
            webbrowser.open(written.as_uri())
        except Exception as exc:  # pragma: no cover
            print(f"Warning: bloom written but browser launch failed: {exc}")
    return written


def launch_live_bloom(
    output_path: Path | None = None,
    *,
    refresh_seconds: float = 2.0,
    duration: float | None = None,
    open_browser: bool = True,
) -> Path:
    """Generate bloom HTML once and keep updating live JSON params until interrupted."""
    interval = max(refresh_seconds, 0.2)
    target = output_path or Path("/tmp/phios_bloom.html")
    params_path = target.with_suffix(".params.json")
    params_uri = params_path.name

    written = target
    try:
        field_data, status_data = poll_kernel_state()
        first_mapped = map_kernel_to_visual_params(field_data, status_data)
        first_params = _with_live_contract(first_mapped, mode="live", refresh_seconds=interval)

        write_live_params_json(first_params, params_path)
        html = render_bloom_html(
            first_params,
            live_mode=True,
            refresh_seconds=interval,
            params_path=params_uri,
        )
        written = write_bloom_file(html, target)

        if open_browser:
            try:
                webbrowser.open(written.as_uri())
            except Exception as exc:  # pragma: no cover
                print(f"Warning: bloom written but browser launch failed: {exc}")

        start = time.monotonic()
        while True:
            if duration is not None and (time.monotonic() - start) >= duration:
                return written

            time.sleep(interval)
            field_data, status_data = poll_kernel_state()
            mapped = map_kernel_to_visual_params(field_data, status_data)
            params = _with_live_contract(mapped, mode="live", refresh_seconds=interval)
            write_live_params_json(params, params_path)
    except KeyboardInterrupt:
        return written
