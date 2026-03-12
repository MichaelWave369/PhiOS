"""Hemavit / TIEKAT observatory interpretation layer for PhiOS.

Boundary contract:
- PhiKernel remains the runtime source of truth for anchor/heart/coherence/capsules/router safety.
- PhiOS observatory values here are symbolic interpretations for operator guidance.
- Z_Hemawit terms are mapping language, not claims of closed physical law.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from phios.adapters.phik import PhiKernelCLIAdapter


def _capsule_count(capsules: dict[str, object]) -> int:
    items = capsules.get("capsules", [])
    if isinstance(items, list):
        return len(items)
    return int(capsules.get("count", 0) or 0)


def _anchor_state(anchor: dict[str, object]) -> str:
    if any(bool(anchor.get(k)) for k in ("verified", "exists", "present", "initialized")):
        return "verified"
    return "missing_or_unverified"


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def zhemawit_mapping_table() -> dict[str, str]:
    return {
        "C_landscape": "Coherence frame space interpreted from PhiKernel field outputs.",
        "dμ Consciousness": "Operator observation delta over runtime snapshots and command responses.",
        "S_ent": "Fragmentation/entropy interpretation from coherence fragmentation signals.",
        "I_info": "Information-density/quality interpretation from field and route signals.",
        "Q_vac": "Reserved field-energy namespace for future symbolic expansion.",
        "O_observer": "Operator + PhiOS shell observation layer over PhiKernel runtime truth.",
        "R_collapse": "Checkpoint/restore transition risk zone in runtime operations.",
        "Z_Hemawit": "Total observatory interpretation frame composed by PhiOS from PhiKernel truth.",
    }


def build_observatory_frame(
    status: dict[str, object],
    field: dict[str, object],
    anchor: dict[str, object],
    capsules: dict[str, object],
) -> dict[str, object]:
    capsule_count = _capsule_count(capsules)
    fragmentation = _number(field.get("fragmentation_score"), 0.0)
    distance = _number(field.get("distance_to_C_star"), 0.0)
    phi_flow = _number(field.get("phi_flow"), 0.0)

    collapse_risk = "elevated" if fragmentation > 0.45 or distance > 0.45 else "managed"
    observer_stability = "steady" if phi_flow >= 0.5 and collapse_risk == "managed" else "watchful"
    recognition_readiness = "high" if collapse_risk == "managed" and capsule_count > 0 else "forming"

    return {
        "anchor_state": _anchor_state(anchor),
        "current_field_action": field.get("recommended_action", field.get("field_action", "unknown")),
        "drift_band": field.get("field_band", field.get("drift_band", "unknown")),
        "capsule_continuity_count": capsule_count,
        "C_landscape_state": "convergent" if distance <= 0.35 else "transitional",
        "observer_stability": observer_stability,
        "entropy_gradient_state": "rising" if fragmentation > 0.35 else "contained",
        "information_gradient_state": "rich" if phi_flow >= 0.55 else "conserving",
        "collapse_risk": collapse_risk,
        "recognition_readiness": recognition_readiness,
        "zhemawit_mode": "observatory-symbolic",
    }


def build_observatory_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = adapter.status()
    field = adapter.field()
    anchor = adapter.anchor_show()
    capsules = adapter.capsule_list()
    frame = build_observatory_frame(status, field, anchor, capsules)
    return {
        "status": status,
        "field": field,
        "anchor": anchor,
        "capsules": capsules,
        "observatory_frame": frame,
        "symbolic_mapping": zhemawit_mapping_table(),
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


def export_observatory_bundle(adapter: PhiKernelCLIAdapter, path_str: str) -> Path:
    target = _validate_export_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = build_observatory_report(adapter)
    payload = {
        "metadata": {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "PhiOS Hemavit Observatory",
        },
        "status": report["status"],
        "field": report["field"],
        "observatory_frame": report["observatory_frame"],
        "symbolic_mapping": report["symbolic_mapping"],
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
