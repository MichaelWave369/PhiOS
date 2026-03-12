"""PhiOS Session Layer composition service.

Boundary contract:
- PhiKernel remains source-of-truth for runtime state.
- PhiOS session outputs are workflow composition over existing wrappers.
- This layer does not replace PhiKernel runtime engines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.hemavit_observatory import build_observatory_report
from phios.core.phik_service import build_coherence_report, build_status_report
from phios.core.psi_mind_observatory import build_psi_mind_report


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


def build_session_start_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = build_status_report(adapter)
    observatory = build_observatory_report(adapter)
    mind = build_psi_mind_report(adapter)

    anchor_ready = status.get("anchor_verification_state", "unknown")
    heart_present = status.get("heart_state", "unknown")
    field_action = status.get("field_action", "unknown")
    observatory_frame_obj = observatory.get("observatory_frame")
    if isinstance(observatory_frame_obj, dict):
        observatory_frame: dict[str, object] = observatory_frame_obj
        observatory_mode = observatory_frame.get("zhemawit_mode", "unknown")
    else:
        observatory_mode = "unknown"

    mind_frame_obj = mind.get("mind_observatory_frame")
    if isinstance(mind_frame_obj, dict):
        mind_frame: dict[str, object] = mind_frame_obj
        mind_mode = mind_frame.get("mind_mode", "unknown")
    else:
        mind_mode = "unknown"

    next_step = "Run: phi session checkin"
    return {
        "anchor_readiness": anchor_ready,
        "heart_presence": heart_present,
        "field_action": field_action,
        "observatory_mode": observatory_mode,
        "mind_mode": mind_mode,
        "next_recommended_step": next_step,
        "status": status,
        "observatory": observatory,
        "mind": mind,
    }


def build_session_checkin_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = build_status_report(adapter)
    coherence = build_coherence_report(adapter)
    observatory = build_observatory_report(adapter)
    mind = build_psi_mind_report(adapter)

    field_state = {
        "action": status.get("field_action", "unknown"),
        "drift_band": status.get("field_drift_band", "unknown"),
        "distance_to_C_star": coherence.get("distance_to_C_star"),
    }

    observatory_frame = observatory.get("observatory_frame", {})
    mind_frame = mind.get("mind_observatory_frame", {})

    session_state = "steady"
    if isinstance(observatory_frame, dict) and observatory_frame.get("collapse_risk") == "elevated":
        session_state = "watchful"
    if isinstance(mind_frame, dict) and mind_frame.get("collapse_risk") == "elevated":
        session_state = "watchful"

    recommended_action = status.get("field_action", "maintain")
    recommended_prompt = "What one grounded next step should I take now?"
    next_step = "Run: phi ask \"What one grounded next step should I take now?\""

    return {
        "session_state": session_state,
        "field_state": field_state,
        "observatory_state": observatory_frame,
        "mind_state": mind_frame,
        "recommended_action": recommended_action,
        "recommended_prompt": recommended_prompt,
        "next_step": next_step,
        "status": status,
        "coherence": coherence,
        "observatory": observatory,
        "mind": mind,
    }


def export_session_bundle(adapter: PhiKernelCLIAdapter, path_str: str) -> Path:
    target = _validate_export_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)

    status = build_status_report(adapter)
    coherence = build_coherence_report(adapter)
    observatory = build_observatory_report(adapter)
    mind = build_psi_mind_report(adapter)
    session_summary = build_session_checkin_report(adapter)

    payload: dict[str, Any] = {
        "metadata": {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "PhiOS Session Layer",
        },
        "status": status,
        "coherence": coherence,
        "hemavit_observatory_frame": observatory.get("observatory_frame", {}),
        "psi_mind_observatory_frame": mind.get("mind_observatory_frame", {}),
        "session_summary": {
            "session_state": session_summary.get("session_state"),
            "field_state": session_summary.get("field_state"),
            "recommended_action": session_summary.get("recommended_action"),
            "recommended_prompt": session_summary.get("recommended_prompt"),
            "next_step": session_summary.get("next_step"),
        },
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
