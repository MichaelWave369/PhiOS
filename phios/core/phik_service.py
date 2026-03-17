"""PhiOS Phase 1 service composition on top of PhiKernel outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.adapters.phik import (
    PhiKernelAdapterError,
    PhiKernelCLIAdapter,
    PhiKernelUnavailableError,
)
from phios.core.kernel_rollout import recent_rollout_status
from phios.core.kernel_runtime import run_kernel_runtime


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _capsule_count(capsules: dict[str, object]) -> int:
    capsule_items = capsules.get("capsules", [])
    if isinstance(capsule_items, list):
        return len(capsule_items)
    count_val = capsules.get("count", 0) or 0
    return _as_int(count_val, default=0)


def _anchor_verification_state(status: dict[str, object]) -> object:
    direct = status.get("anchor_verification_state")
    if direct is not None:
        return direct
    anchor_obj = status.get("anchor")
    if isinstance(anchor_obj, dict):
        anchor_dict: dict[str, object] = anchor_obj
        return anchor_dict.get("verification_state", "unknown")
    return "unknown"


def _heart_state(status: dict[str, object]) -> object:
    direct = status.get("heart_state")
    if direct is not None:
        return direct
    heart_obj = status.get("heart")
    if isinstance(heart_obj, dict):
        heart_dict: dict[str, object] = heart_obj
        return heart_dict.get("state", "unknown")
    return "unknown"


def build_status_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = adapter.status()
    field = adapter.field()
    capsules = adapter.capsule_list()

    report = {
        "anchor_verification_state": _anchor_verification_state(status),
        "heart_state": _heart_state(status),
        "field_action": field.get("recommended_action", field.get("field_action", "unknown")),
        "field_drift_band": field.get("field_band", field.get("drift_band", "unknown")),
        "capsule_count": _capsule_count(capsules),
        "phik_status": status,
    }
    try:
        runtime = run_kernel_runtime(adapter, context_type="status", source_label="phi status")
    except PhiKernelAdapterError as exc:
        report["kernel_runtime"] = {"enabled": True, "error": str(exc)}
    else:
        report["kernel_runtime"] = runtime
        report["kernel_rollout"] = recent_rollout_status()
    return report


def build_coherence_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    field = adapter.field()
    return {
        "C_current": field.get("C_current"),
        "C_star": field.get("C_star"),
        "distance_to_C_star": field.get("distance_to_C_star"),
        "phi_flow": field.get("phi_flow"),
        "lambda_node": field.get("lambda_node"),
        "sigma_feedback": field.get("sigma_feedback"),
        "fragmentation_score": field.get("fragmentation_score"),
        "recommended_action": field.get("recommended_action"),
        "phik_field": field,
    }


def build_ask_report(adapter: PhiKernelCLIAdapter, prompt: str) -> dict[str, object]:
    runtime = run_kernel_runtime(adapter, prompt=prompt, context_type="ask", source_label="phi ask")
    if runtime.get("enabled"):
        primary = runtime.get("primary", {})
        recommendation = primary.get("recommendation")
        return {
            "prompt": prompt,
            "coach": "PhiKernelRuntime",
            "field_action": primary.get("verdict"),
            "field_band": primary.get("mode"),
            "safety_posture": primary.get("evidence_level"),
            "route_reason": f"adapter={primary.get('adapter', 'unknown')}",
            "body": recommendation,
            "next_actions": [recommendation] if recommendation else [],
            "kernel_runtime": runtime,
            "phik_ask": {},
        }

    data = adapter.ask(prompt)
    return {
        "prompt": prompt,
        "coach": data.get("coach"),
        "field_action": data.get("field_action"),
        "field_band": data.get("field_band"),
        "safety_posture": data.get("safety_posture"),
        "route_reason": data.get("route_reason"),
        "body": data.get("body"),
        "next_actions": data.get("next_actions"),
        "kernel_runtime": runtime,
        "phik_ask": data,
    }


def _anchor_exists(anchor: dict[str, object]) -> bool:
    candidates = [
        anchor.get("exists"),
        anchor.get("present"),
        anchor.get("initialized"),
        anchor.get("verified"),
        anchor.get("anchor_id"),
    ]
    return any(bool(item) for item in candidates)


def _heart_exists(status: dict[str, object]) -> bool:
    heart = status.get("heart")
    if isinstance(heart, dict):
        heart_dict: dict[str, object] = heart
        if any(k in heart_dict for k in ("status", "state", "running", "present")):
            return True
    heart_state = status.get("heart_state")
    return bool(heart_state and str(heart_state).lower() not in {"missing", "none", "null"})


def build_doctor_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    if not adapter.is_available():
        return {
            "status": "missing_phik",
            "checks": {
                "phik_callable": False,
                "anchor_exists": False,
                "heart_status_exists": False,
                "coherence_frame_exists": False,
                "capsule_entries": 0,
            },
            "message": "PhiKernel CLI `phik` is missing. Install PhiKernel and initialize before using PhiOS wrappers.",
        }

    try:
        status = adapter.status()
        field = adapter.field()
        anchor = adapter.anchor_show()
        capsules = adapter.capsule_list()
    except PhiKernelUnavailableError:
        return {
            "status": "missing_phik",
            "checks": {
                "phik_callable": False,
                "anchor_exists": False,
                "heart_status_exists": False,
                "coherence_frame_exists": False,
                "capsule_entries": 0,
            },
            "message": "PhiKernel CLI `phik` is missing. Install PhiKernel and initialize before using PhiOS wrappers.",
        }
    except PhiKernelAdapterError as exc:
        return {
            "status": "degraded",
            "checks": {
                "phik_callable": True,
                "anchor_exists": False,
                "heart_status_exists": False,
                "coherence_frame_exists": False,
                "capsule_entries": 0,
            },
            "message": str(exc),
        }

    anchor_exists = _anchor_exists(anchor)
    heart_exists = _heart_exists(status)
    coherence_exists = bool(field)
    capsule_entries = _capsule_count(capsules)

    state = "ready"
    if not anchor_exists:
        state = "needs_init"
    elif not heart_exists or not coherence_exists or capsule_entries == 0:
        state = "needs_pulse"

    return {
        "status": state,
        "checks": {
            "phik_callable": True,
            "anchor_exists": anchor_exists,
            "heart_status_exists": heart_exists,
            "coherence_frame_exists": coherence_exists,
            "capsule_entries": capsule_entries,
        },
        "raw": {
            "status": status,
            "field": field,
            "anchor": anchor,
            "capsules": capsules,
        },
        "message": "PhiKernel readiness inspection completed.",
    }


def run_init(
    adapter: PhiKernelCLIAdapter,
    *,
    passphrase: str,
    sovereign_name: str,
    user_label: str,
    resonant_label: str | None = None,
) -> dict[str, object]:
    return adapter.init(
        passphrase=passphrase,
        sovereign_name=sovereign_name,
        user_label=user_label,
        resonant_label=resonant_label,
    )


def run_pulse_once(
    adapter: PhiKernelCLIAdapter,
    *,
    checkpoint: str | None = None,
    passphrase: str | None = None,
) -> dict[str, object]:
    return adapter.pulse_once(checkpoint=checkpoint, passphrase=passphrase)


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


def export_phase1_bundle(adapter: PhiKernelCLIAdapter, path_str: str) -> Path:
    target = _validate_export_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "metadata": {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "PhiOS Phase 1",
        },
        "status": adapter.status(),
        "field": adapter.field(),
        "anchor": adapter.anchor_show(),
        "capsules": adapter.capsule_list(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
