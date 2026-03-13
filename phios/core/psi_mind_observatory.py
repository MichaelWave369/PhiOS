"""Psi-mind observatory interpretation layer for PhiOS.

Boundary contract:
- PhiKernel remains the runtime source-of-truth for anchor/heart/coherence/capsules/router safety.
- PhiOS exposes symbolic mind-observatory interpretations for operator ergonomics.
- Psi-mind/Hemawit terms are runtime mappings, not closed-physics claims.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.adapters.phik import PhiKernelCLIAdapter


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


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _capsule_count(capsules: dict[str, object]) -> int:
    items = capsules.get("capsules", [])
    if isinstance(items, list):
        return len(items)
    count_val = capsules.get("count", 0) or 0
    return _as_int(count_val, default=0)


def _anchor_state(anchor: dict[str, object]) -> str:
    if any(bool(anchor.get(k)) for k in ("verified", "exists", "present", "initialized")):
        return "verified"
    return "missing_or_unverified"


def psi_mind_mapping_table() -> dict[str, str]:
    return {
        "Ψ_mind": "Interpreted current mind-field state from PhiKernel runtime signals.",
        "V(Ψ)": "Active inner-state potential/affective loading namespace.",
        "ξRΨ": "Coupling between runtime structure and field state.",
        "λI": "Information-density interpretation over runtime frame quality.",
        "ηS_ent": "Entropy/fragmentation interpretation from field signals.",
        "κC": "Coherence contribution interpreted from PhiKernel field state.",
        "K(x-y)Ψ(y)": "Symbolic nonlocal memory/retrieval/music-kernel interpretation.",
        "γ Σ⟨Ψ_i|Ψ_j⟩": "Overlap/relational resonance interpretation.",
        "L_obs(Ψ,O)": "Observer/operator interaction layer.",
        "L_topology": "Symbolic high-order topology namespace.",
        "M_multiverse": "Symbolic branching/possibility namespace.",
        "R_collapse": "Checkpoint/restore transition zone.",
    }


def build_psi_mind_frame(
    status: dict[str, object],
    field: dict[str, object],
    anchor: dict[str, object],
    capsules: dict[str, object],
) -> dict[str, object]:
    _ = status
    capsule_count = _capsule_count(capsules)
    fragmentation = _number(field.get("fragmentation_score"), 0.0)
    phi_flow = _number(field.get("phi_flow"), 0.0)
    distance = _number(field.get("distance_to_C_star"), 0.0)

    entropy_load = "high" if fragmentation > 0.45 else "moderate" if fragmentation > 0.25 else "light"
    information_density = "rich" if phi_flow >= 0.55 else "forming"
    observer_coupling = "aligned" if distance <= 0.35 else "seeking"
    collapse_risk = "elevated" if fragmentation > 0.45 or distance > 0.45 else "managed"
    kernel_resonance = "strong" if phi_flow >= 0.6 and distance <= 0.3 else "present"
    overlap_strength = "high" if capsule_count >= 3 else "emerging" if capsule_count > 0 else "minimal"
    recognition_readiness = "high" if collapse_risk == "managed" and capsule_count > 0 else "forming"

    return {
        "anchor_state": _anchor_state(anchor),
        "current_field_action": field.get("recommended_action", field.get("field_action", "unknown")),
        "drift_band": field.get("field_band", field.get("drift_band", "unknown")),
        "capsule_continuity_count": capsule_count,
        "psi_mind_state": "coherent" if distance <= 0.35 else "transitional",
        "observer_coupling": observer_coupling,
        "entropy_load": entropy_load,
        "information_density": information_density,
        "kernel_resonance": kernel_resonance,
        "overlap_strength": overlap_strength,
        "collapse_risk": collapse_risk,
        "recognition_readiness": recognition_readiness,
        "mind_mode": "psi_mind_observatory",
    }


def build_psi_mind_report(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    status = adapter.status()
    field = adapter.field()
    anchor = adapter.anchor_show()
    capsules = adapter.capsule_list()
    frame = build_psi_mind_frame(status, field, anchor, capsules)
    return {
        "status": status,
        "field": field,
        "anchor": anchor,
        "capsules": capsules,
        "mind_observatory_frame": frame,
        "symbolic_mapping": psi_mind_mapping_table(),
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


def export_psi_mind_bundle(adapter: PhiKernelCLIAdapter, path_str: str) -> Path:
    target = _validate_export_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = build_psi_mind_report(adapter)
    payload: dict[str, Any] = {
        "metadata": {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "PhiOS PsiMind Observatory",
        },
        "status": report["status"],
        "field": report["field"],
        "mind_observatory_frame": report["mind_observatory_frame"],
        "symbolic_mapping": report["symbolic_mapping"],
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
