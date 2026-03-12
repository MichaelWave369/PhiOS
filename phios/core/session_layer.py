"""PhiOS Session Layer composition service.

Boundary contract:
- PhiKernel remains source-of-truth for runtime state.
- Session-layer values are PhiOS-level interpretations for operator workflow.
- Hemawit/observer/self terms are symbolic runtime mappings, not physical-law claims.
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


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _entropy_load(fragmentation: object) -> str:
    frag = float(fragmentation) if isinstance(fragmentation, (int, float)) else 0.0
    if frag > 0.45:
        return "high"
    if frag > 0.25:
        return "moderate"
    return "light"


def _observer_state(collapse_risk: object) -> str:
    return "attentive" if collapse_risk == "elevated" else "grounded"


def _self_alignment(distance_to_c_star: object) -> str:
    distance = float(distance_to_c_star) if isinstance(distance_to_c_star, (int, float)) else 0.0
    if distance <= 0.3:
        return "aligned"
    if distance <= 0.5:
        return "re-centering"
    return "recovering"


def _emergence_pressure(recommended_action: object, collapse_risk: object) -> str:
    if collapse_risk == "elevated":
        return "high"
    if isinstance(recommended_action, str) and recommended_action.lower() not in {"maintain", "hold", "unknown"}:
        return "building"
    return "steady"


def build_session_start_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = build_status_report(adapter)
    observatory = build_observatory_report(adapter)
    mind = build_psi_mind_report(adapter)

    observatory_frame = _as_dict(observatory.get("observatory_frame"))
    mind_frame = _as_dict(mind.get("mind_observatory_frame"))

    collapse_risk = mind_frame.get("collapse_risk", observatory_frame.get("collapse_risk", "managed"))
    observer_state = _observer_state(collapse_risk)
    self_alignment = _self_alignment(status.get("field_drift_band"))

    session_state = "watchful" if collapse_risk == "elevated" else "steady"

    # Keep both new and prior key names to preserve existing consumers.
    return {
        "session_state": session_state,
        "anchor_ready": status.get("anchor_verification_state", "unknown"),
        "heart_ready": status.get("heart_state", "unknown"),
        "field_action": status.get("field_action", "unknown"),
        "drift_band": status.get("field_drift_band", "unknown"),
        "observatory_mode": observatory_frame.get("zhemawit_mode", "unknown"),
        "mind_mode": mind_frame.get("mind_mode", "unknown"),
        "observer_state": observer_state,
        "self_alignment": self_alignment,
        "next_step": "Run: phi session checkin",
        "anchor_readiness": status.get("anchor_verification_state", "unknown"),
        "heart_presence": status.get("heart_state", "unknown"),
        "next_recommended_step": "Run: phi session checkin",
        "status": status,
        "observatory": observatory,
        "mind": mind,
    }


def build_session_checkin_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = build_status_report(adapter)
    coherence = build_coherence_report(adapter)
    observatory = build_observatory_report(adapter)
    mind = build_psi_mind_report(adapter)

    observatory_state = _as_dict(observatory.get("observatory_frame"))
    mind_state = _as_dict(mind.get("mind_observatory_frame"))

    field_state = {
        "action": status.get("field_action", "unknown"),
        "drift_band": status.get("field_drift_band", "unknown"),
        "distance_to_C_star": coherence.get("distance_to_C_star"),
    }

    collapse_risk = mind_state.get("collapse_risk", observatory_state.get("collapse_risk", "managed"))
    recognition_readiness = mind_state.get(
        "recognition_readiness",
        observatory_state.get("recognition_readiness", "forming"),
    )
    information_density = mind_state.get("information_density", "forming")
    entropy_load = mind_state.get("entropy_load", _entropy_load(coherence.get("fragmentation_score")))
    observer_state = _observer_state(collapse_risk)
    self_alignment = _self_alignment(coherence.get("distance_to_C_star"))
    emergence_pressure = _emergence_pressure(status.get("field_action"), collapse_risk)
    zhemawit_mode = observatory_state.get("zhemawit_mode", "observatory-symbolic")

    session_state = "watchful" if collapse_risk == "elevated" else "steady"
    recommended_action = status.get("field_action", "maintain")
    recommended_prompt = "What one grounded next step should I take now?"
    next_step = f'Run: phi ask "{recommended_prompt}"'

    return {
        "session_state": session_state,
        "field_state": field_state,
        "observatory_state": observatory_state,
        "mind_state": mind_state,
        "observer_state": observer_state,
        "self_alignment": self_alignment,
        "information_density": information_density,
        "entropy_load": entropy_load,
        "emergence_pressure": emergence_pressure,
        "collapse_risk": collapse_risk,
        "recognition_readiness": recognition_readiness,
        "recommended_action": recommended_action,
        "recommended_prompt": recommended_prompt,
        "next_step": next_step,
        "zhemawit_mode": zhemawit_mode,
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
        "symbolic_session_fields": {
            "observer_state": session_summary.get("observer_state"),
            "self_alignment": session_summary.get("self_alignment"),
            "information_density": session_summary.get("information_density"),
            "entropy_load": session_summary.get("entropy_load"),
            "emergence_pressure": session_summary.get("emergence_pressure"),
            "zhemawit_mode": session_summary.get("zhemawit_mode"),
            "G_info(I)": session_summary.get("information_density"),
            "η S_ent": session_summary.get("entropy_load"),
            "T_emerge": session_summary.get("emergence_pressure"),
            "O_observer": session_summary.get("observer_state"),
            "U_self": session_summary.get("self_alignment"),
            "Z_Hemawit": session_summary.get("zhemawit_mode"),
        },
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
