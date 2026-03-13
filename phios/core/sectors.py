"""Experimental symbolic sector ontology for PhiOS observatory surfacing.

These sectors are UI/analysis ontology scaffolds (HG/HB families), not validated
physical-law claims.
"""

from __future__ import annotations


SECTOR_ONTOLOGY: dict[str, list[dict[str, object]]] = {
    "HG": [
        {"sector_id": "geometry", "display_name": "Geometry", "family": "HG", "description": "Shape/curvature symbolic sector.", "category": "structure", "symbol_refs": ["g", "R"], "heat_modes": ["geometry_balance"], "dashboard_panel": "geometry", "color_hint": "indigo"},
        {"sector_id": "vacuum", "display_name": "Vacuum", "family": "HG", "description": "Vacuum/coherence symbolic sector.", "category": "coherence", "symbol_refs": ["vac"], "heat_modes": ["vacuum_proximity"], "dashboard_panel": "vacuum", "color_hint": "cyan"},
        {"sector_id": "scalar_field", "display_name": "Scalar Field", "family": "HG", "description": "Scalar field scaffold sector.", "category": "field", "symbol_refs": ["phi"], "dashboard_panel": "scalar_field", "color_hint": "violet"},
        {"sector_id": "mirror", "display_name": "Mirror", "family": "HG", "description": "Mirror/reflection symbolic sector.", "category": "relation", "symbol_refs": ["M"], "heat_modes": ["mirror_alignment"], "dashboard_panel": "mirror", "color_hint": "silver"},
        {"sector_id": "observer", "display_name": "Observer", "family": "HG", "description": "Observer/measurement scaffold sector.", "category": "agent", "symbol_refs": ["O"], "heat_modes": ["observer_entropy"], "dashboard_panel": "observer", "color_hint": "amber"},
        {"sector_id": "entropy", "display_name": "Entropy", "family": "HG", "description": "Entropy/disorder symbolic sector.", "category": "thermo", "symbol_refs": ["S"], "dashboard_panel": "entropy", "color_hint": "orange"},
        {"sector_id": "collector", "display_name": "Collector", "family": "HG", "description": "Collection/memory scaffold sector.", "category": "memory", "symbol_refs": ["C"], "heat_modes": ["collector_activity"], "dashboard_panel": "collector", "color_hint": "green"},
        {"sector_id": "loop", "display_name": "Loop", "family": "HG", "description": "Loop/feedback symbolic sector.", "category": "dynamics", "symbol_refs": ["L"], "dashboard_panel": "loop", "color_hint": "teal"},
    ],
    "HB": [
        {"sector_id": "matter_energy", "display_name": "Matter/Energy", "family": "HB", "description": "Operational matter-energy scaffold.", "category": "runtime", "symbol_refs": ["rho"], "dashboard_panel": "matter_energy", "color_hint": "red"},
        {"sector_id": "mirror", "display_name": "Mirror", "family": "HB", "description": "Reflection/dual scaffold.", "category": "relation", "symbol_refs": ["M"], "heat_modes": ["mirror_alignment"], "dashboard_panel": "mirror", "color_hint": "silver"},
        {"sector_id": "scalar_gradient", "display_name": "Scalar Gradient", "family": "HB", "description": "Scalar gradient symbolic operational term.", "category": "field", "symbol_refs": ["grad(phi)"], "dashboard_panel": "scalar_gradient", "color_hint": "violet"},
        {"sector_id": "gravitational_stress", "display_name": "Gravitational Stress", "family": "HB", "description": "Stress/strain symbolic runtime term.", "category": "stress", "symbol_refs": ["sigma_g"], "dashboard_panel": "gravitational_stress", "color_hint": "brown"},
        {"sector_id": "vacuum", "display_name": "Vacuum", "family": "HB", "description": "Vacuum/coherence operational scaffold.", "category": "coherence", "symbol_refs": ["vac"], "heat_modes": ["vacuum_proximity"], "dashboard_panel": "vacuum", "color_hint": "cyan"},
        {"sector_id": "emotion", "display_name": "Emotion", "family": "HB", "description": "Affective operator context scaffold.", "category": "operator", "symbol_refs": ["E"], "heat_modes": ["emotion_field"], "dashboard_panel": "emotion", "color_hint": "pink"},
        {"sector_id": "collector", "display_name": "Collector", "family": "HB", "description": "Operator collection/memory scaffold.", "category": "memory", "symbol_refs": ["C"], "heat_modes": ["collector_activity"], "dashboard_panel": "collector", "color_hint": "green"},
    ],
}


def list_visual_bloom_sectors(family: str | None = None) -> list[dict[str, object]]:
    if family is None:
        return [dict(row) for rows in SECTOR_ONTOLOGY.values() for row in rows]
    fam = family.strip().upper()
    return [dict(row) for row in SECTOR_ONTOLOGY.get(fam, [])]


def get_visual_bloom_sector(sector_id: str, family: str | None = None) -> dict[str, object] | None:
    sid = sector_id.strip().lower()
    rows = list_visual_bloom_sectors(family)
    for row in rows:
        if str(row.get("sector_id", "")).lower() == sid:
            return dict(row)
    return None


def _to_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def infer_visual_bloom_sector_weights(metadata: dict[str, object]) -> dict[str, float]:
    """Heuristic sector weights from local metadata (experimental)."""
    coherence = _to_float(metadata.get("coherenceC"), 0.809)
    frequency = _to_float(metadata.get("frequency"), 7.83)
    noise = _to_float(metadata.get("noiseScale"), 0.005)
    tags_obj = metadata.get("tags")
    tag_count = float(len(tags_obj)) if isinstance(tags_obj, list) else 0.0

    out = {
        "geometry": max(0.0, min(1.0, 1.0 - noise * 100.0)),
        "vacuum": max(0.0, min(1.0, coherence)),
        "observer": max(0.0, min(1.0, 0.5 + tag_count * 0.05)),
        "entropy": max(0.0, min(1.0, noise * 120.0)),
        "collector": max(0.0, min(1.0, 0.3 + tag_count * 0.07)),
        "mirror": max(0.0, min(1.0, abs(frequency - 7.83) / 10.0)),
        "emotion": max(0.0, min(1.0, abs(coherence - 0.81055) * 25.0)),
    }
    total = sum(out.values())
    if total <= 1e-12:
        return {k: 0.0 for k in out}
    return {k: v / total for k, v in out.items()}


def dominant_sector(weights: dict[str, float]) -> str:
    if not weights:
        return ""
    return max(weights.items(), key=lambda kv: kv[1])[0]
