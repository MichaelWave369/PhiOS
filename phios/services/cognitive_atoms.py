"""Experimental sector-to-cognitive-atom mapping service."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.constants import BIO_VACUUM_TARGET, C_STAR_THEORETICAL, HUNTER_C_STATUS
from phios.core.session_layer import build_session_checkin_report


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_level(value: object, default: float) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        named_levels = {
            "low": 0.2,
            "moderate": 0.5,
            "medium": 0.5,
            "high": 0.85,
            "aligned": 0.82,
            "re-centering": 0.55,
            "misaligned": 0.2,
            "grounded": 0.5,
            "attentive": 0.75,
            "overloaded": 0.9,
            "calm": 0.3,
            "neutral": 0.5,
            "elevated": 0.75,
        }
        if normalized in named_levels:
            return named_levels[normalized]
    return _as_float(value, default)


def build_sector_atom_context(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Build a read-only, deterministic sector-state context for atom mapping."""

    try:
        checkin = build_session_checkin_report(adapter)
    except Exception:
        checkin = {}

    checkin_dict: dict[str, object] = checkin if isinstance(checkin, dict) else {}

    try:
        field_raw = adapter.field() if hasattr(adapter, "field") else {}
    except Exception:
        field_raw = {}
    field_state: dict[str, object] = field_raw if isinstance(field_raw, dict) else {}

    coherence_obj = checkin_dict.get("coherence", {})
    coherence: dict[str, object] = coherence_obj if isinstance(coherence_obj, dict) else {}

    c_current = _as_float(coherence.get("C_current", field_state.get("C_current")), 0.5)
    distance_to_c_star = _as_float(
        coherence.get("distance_to_C_star", field_state.get("distance_to_C_star")),
        abs(c_current - C_STAR_THEORETICAL),
    )
    vacuum_proximity = _clamp(
        _as_float(
            checkin_dict.get("vacuum_proximity", field_state.get("vacuum_proximity")),
            1.0 - distance_to_c_star / max(C_STAR_THEORETICAL, 1e-6),
        ),
        0.0,
        1.0,
    )

    sector_state = {
        "geometry_balance": _clamp(
            _as_level(checkin_dict.get("geometry_balance", field_state.get("geometry_balance")), 0.5),
            0.0,
            1.0,
        ),
        "vacuum_proximity": vacuum_proximity,
        "observer_entropy": _clamp(
            _as_level(checkin_dict.get("observer_entropy", checkin_dict.get("entropy_load")), 0.5),
            0.0,
            1.0,
        ),
        "collector_activity": _clamp(
            _as_level(checkin_dict.get("collector_activity", field_state.get("collector_activity")), 0.5),
            0.0,
            1.0,
        ),
        "mirror_alignment": _clamp(
            _as_level(checkin_dict.get("mirror_alignment", checkin_dict.get("self_alignment")), 0.55),
            0.0,
            1.0,
        ),
        "emotion_field": _clamp(
            _as_level(checkin_dict.get("emotion_field", checkin_dict.get("observer_state")), 0.5),
            0.0,
            1.0,
        ),
    }

    return {
        "generated_at": _utc_now_iso(),
        "source": "phios.session_checkin+field_state",
        "coherence_current": c_current,
        "distance_to_c_star": distance_to_c_star,
        "sector_state": sector_state,
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
    }


def sector_to_cognitive_atoms(sector_state: dict[str, object]) -> dict[str, object]:
    """Map sector-state signals to deterministic cognitive atom overrides."""

    geometry_balance = _clamp(_as_float(sector_state.get("geometry_balance"), 0.5), 0.0, 1.0)
    vacuum_proximity = _clamp(_as_float(sector_state.get("vacuum_proximity"), 0.5), 0.0, 1.0)
    observer_entropy = _clamp(_as_float(sector_state.get("observer_entropy"), 0.5), 0.0, 1.0)
    collector_activity = _clamp(_as_float(sector_state.get("collector_activity"), 0.5), 0.0, 1.0)
    mirror_alignment = _clamp(_as_float(sector_state.get("mirror_alignment"), 0.5), 0.0, 1.0)
    emotion_field = _clamp(_as_float(sector_state.get("emotion_field"), 0.5), 0.0, 1.0)

    atom_overrides: dict[str, object] = {}
    reasons: list[str] = []

    if geometry_balance >= 0.67:
        atom_overrides["epistemic_style"] = "deductive"
        reasons.append("geometry_balance>=0.67 -> epistemic_style=deductive")
    elif geometry_balance <= 0.33:
        atom_overrides["epistemic_style"] = "abductive"
        reasons.append("geometry_balance<=0.33 -> epistemic_style=abductive")
    else:
        atom_overrides["epistemic_style"] = "hybrid"
        reasons.append("0.33<geometry_balance<0.67 -> epistemic_style=hybrid")

    if vacuum_proximity >= 0.75:
        atom_overrides["creativity_level"] = "inventive"
        reasons.append("vacuum_proximity>=0.75 -> creativity_level=inventive")
    else:
        atom_overrides["creativity_level"] = "convergent"
        reasons.append("vacuum_proximity<0.75 -> creativity_level=convergent")

    if observer_entropy >= 0.67:
        atom_overrides["uncertainty_handling"] = "explicit"
        atom_overrides["error_posture"] = "fail_loud"
        reasons.append(
            "observer_entropy>=0.67 -> uncertainty_handling=explicit,error_posture=fail_loud"
        )
    else:
        atom_overrides["uncertainty_handling"] = "probabilistic"
        atom_overrides["error_posture"] = "fail_soft"
        reasons.append(
            "observer_entropy<0.67 -> uncertainty_handling=probabilistic,error_posture=fail_soft"
        )

    if collector_activity >= 0.6:
        atom_overrides["cognitive_rhythm"] = "iterative"
        reasons.append("collector_activity>=0.6 -> cognitive_rhythm=iterative")
    else:
        atom_overrides["cognitive_rhythm"] = "deep_focus"
        reasons.append("collector_activity<0.6 -> cognitive_rhythm=deep_focus")

    if mirror_alignment >= 0.6:
        atom_overrides["collaboration_posture"] = "pair"
        reasons.append("mirror_alignment>=0.6 -> collaboration_posture=pair")
    else:
        atom_overrides["collaboration_posture"] = "solo"
        reasons.append("mirror_alignment<0.6 -> collaboration_posture=solo")

    if emotion_field >= 0.66:
        atom_overrides["communication_style"] = "narrative"
        reasons.append("emotion_field>=0.66 -> communication_style=narrative")
    elif emotion_field <= 0.4:
        atom_overrides["communication_style"] = "technical"
        reasons.append("emotion_field<=0.4 -> communication_style=technical")
    else:
        atom_overrides["communication_style"] = "balanced"
        reasons.append("0.4<emotion_field<0.66 -> communication_style=balanced")

    distances = [
        abs(geometry_balance - 0.5),
        abs(vacuum_proximity - 0.5),
        abs(observer_entropy - 0.5),
        abs(collector_activity - 0.5),
        abs(mirror_alignment - 0.5),
        abs(emotion_field - 0.5),
    ]
    confidence = _clamp(0.55 + (sum(distances) / len(distances)) * 0.6, 0.55, 0.95)

    return {
        "atom_overrides": atom_overrides,
        "reasons": reasons,
        "confidence": round(confidence, 6),
    }


def explain_cognitive_atom_overrides(overrides: dict[str, object]) -> str:
    reasons_obj = overrides.get("reasons", [])
    reasons = reasons_obj if isinstance(reasons_obj, list) else []
    return "; ".join(str(r) for r in reasons)


def recommend_cognitive_atom_overrides(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Compute a read-only, deterministic cognitive atom override recommendation."""

    context = build_sector_atom_context(adapter)
    sector_state_obj = context.get("sector_state", {})
    sector_state: dict[str, object] = sector_state_obj if isinstance(sector_state_obj, dict) else {}
    mapped = sector_to_cognitive_atoms(sector_state)
    return {
        **mapped,
        "reason": explain_cognitive_atom_overrides(mapped),
        "sector_state": sector_state,
        "generated_at": context.get("generated_at", _utc_now_iso()),
        "source": context.get("source", "phios.session_checkin+field_state"),
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
    }
