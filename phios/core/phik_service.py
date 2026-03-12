"""PhiOS Phase 1 service composition on top of PhiKernel outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from phios.adapters.phik import PhiKernelCLIAdapter


def build_status_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = adapter.status()
    field = adapter.field()
    capsules = adapter.capsule_list()

    capsule_items = capsules.get("capsules", [])
    capsule_count = len(capsule_items) if isinstance(capsule_items, list) else int(capsules.get("count", 0) or 0)

    return {
        "anchor_verification_state": status.get("anchor_verification_state", status.get("anchor", {}).get("verification_state") if isinstance(status.get("anchor"), dict) else "unknown"),
        "heart_state": status.get("heart_state", status.get("heart", {}).get("state") if isinstance(status.get("heart"), dict) else "unknown"),
        "field_action": field.get("recommended_action", field.get("field_action", "unknown")),
        "field_drift_band": field.get("field_band", field.get("drift_band", "unknown")),
        "capsule_count": capsule_count,
        "phik_status": status,
    }


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
        "phik_ask": data,
    }


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

    payload = {
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
