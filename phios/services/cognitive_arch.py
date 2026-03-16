"""Experimental field-guided cognitive architecture recommendation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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


@dataclass(frozen=True, slots=True)
class CandidateScore:
    figure: str
    archetype: str
    score: float
    drivers: tuple[str, ...]


def build_cognitive_arch_context(adapter: PhiKernelCLIAdapter) -> dict[str, Any]:
    """Build a stable, read-only context for cognitive-architecture recommendation."""

    try:
        checkin = build_session_checkin_report(adapter)
    except Exception:
        checkin = {
            "observer_state": "grounded",
            "self_alignment": "re-centering",
            "information_density": "forming",
            "entropy_load": "moderate",
            "emergence_pressure": "steady",
            "coherence": {"C_current": 0.5, "distance_to_C_star": 0.5},
            "field_state": {"drift_band": "unknown"},
            "session_state": "steady",
        }

    checkin_dict: dict[str, Any] = checkin if isinstance(checkin, dict) else {}
    coherence_obj = checkin_dict.get("coherence", {})
    coherence: dict[str, Any] = coherence_obj if isinstance(coherence_obj, dict) else {}
    field_obj = checkin_dict.get("field_state", {})
    field_state: dict[str, Any] = field_obj if isinstance(field_obj, dict) else {}
    c_current = _as_float(coherence.get("C_current"), 0.5)
    distance = _as_float(coherence.get("distance_to_C_star"), abs(c_current - C_STAR_THEORETICAL))
    c_star_proximity = _clamp(1.0 - abs(c_current - C_STAR_THEORETICAL) / max(C_STAR_THEORETICAL, 1e-6), 0.0, 1.0)

    return {
        "generated_at": _utc_now_iso(),
        "observer_state": str(checkin_dict.get("observer_state", "grounded")),
        "self_alignment": str(checkin_dict.get("self_alignment", "re-centering")),
        "information_density": str(checkin_dict.get("information_density", "forming")),
        "entropy_load": str(checkin_dict.get("entropy_load", "moderate")),
        "emergence_pressure": str(checkin_dict.get("emergence_pressure", "steady")),
        "session_state": str(checkin_dict.get("session_state", "steady")),
        "drift_band": str(field_state.get("drift_band", checkin_dict.get("drift_band", "unknown"))),
        "coherence_current": c_current,
        "distance_to_c_star": distance,
        "c_star_proximity": c_star_proximity,
        "source": "phios.session_checkin",
        "experimental": True,
    }


def score_cognitive_arch_candidates(context: dict[str, Any]) -> list[CandidateScore]:
    """Score deterministic cognitive-architecture candidates from field signals."""

    emergence = str(context.get("emergence_pressure", "steady")).lower()
    entropy = str(context.get("entropy_load", "moderate")).lower()
    alignment = str(context.get("self_alignment", "re-centering")).lower()
    observer = str(context.get("observer_state", "grounded")).lower()
    density = str(context.get("information_density", "forming")).lower()
    drift_band = str(context.get("drift_band", "unknown")).lower()
    c_proximity = _as_float(context.get("c_star_proximity"), 0.5)
    c_current = _as_float(context.get("coherence_current"), 0.5)

    scored: list[CandidateScore] = []

    def mk(figure: str, archetype: str, score: float, drivers: list[str]) -> None:
        scored.append(CandidateScore(figure=figure, archetype=archetype, score=round(score, 6), drivers=tuple(drivers)))

    explorer_score = 0.2
    explorer_drivers: list[str] = []
    if emergence in {"high", "building"}:
        explorer_score += 0.45
        explorer_drivers.append("emergence pressure favors exploratory decomposition")
    if density in {"high", "saturated"}:
        explorer_score += 0.15
        explorer_drivers.append("high information density benefits inventive parallelism")
    mk("Wayfinder", "exploratory_inventive", explorer_score, explorer_drivers)

    sentinel_score = 0.2
    sentinel_drivers: list[str] = []
    if entropy == "high":
        sentinel_score += 0.5
        sentinel_drivers.append("high entropy load favors guardian fail-loud sequencing")
    elif entropy == "moderate":
        sentinel_score += 0.2
        sentinel_drivers.append("moderate entropy load favors controlled execution")
    if observer == "attentive":
        sentinel_score += 0.1
        sentinel_drivers.append("attentive observer state supports defensive review loops")
    mk("Sentinel", "guardian_fail_loud_craftsman", sentinel_score, sentinel_drivers)

    architect_score = 0.2
    architect_drivers: list[str] = []
    if alignment == "aligned":
        architect_score += 0.45
        architect_drivers.append("high self-alignment supports deductive deep-focus planning")
    elif alignment == "re-centering":
        architect_score += 0.2
        architect_drivers.append("re-centering alignment favors structured architecture")
    if density in {"forming", "sparse"}:
        architect_score += 0.1
        architect_drivers.append("lower information density benefits deliberate decomposition")
    mk("Architect", "deductive_deep_focus", architect_score, architect_drivers)

    mediator_score = 0.2
    mediator_drivers: list[str] = []
    if c_current < 0.55 or drift_band in {"red", "amber", "recovering"}:
        mediator_score += 0.45
        mediator_drivers.append("low coherence/oscillation favors consultative uncertainty-aware mode")
    if observer == "attentive":
        mediator_score += 0.1
        mediator_drivers.append("attentive observer state suggests explicit confirmation steps")
    mk("Mediator", "pragmatist_consultative", mediator_score, mediator_drivers)

    visionary_score = 0.2
    visionary_drivers: list[str] = []
    if c_proximity >= 0.92:
        visionary_score += 0.55
        visionary_drivers.append("near theoretical C* supports analogical associative synthesis")
    elif c_proximity >= 0.8:
        visionary_score += 0.25
        visionary_drivers.append("moderate C* proximity supports synthesis-forward planning")
    if emergence in {"high", "building"}:
        visionary_score += 0.1
        visionary_drivers.append("emergence pressure supports generative pattern search")
    mk("Visionary", "analogical_associative", visionary_score, visionary_drivers)

    return sorted(scored, key=lambda item: (-item.score, item.figure))


def explain_cognitive_arch_recommendation(recommendation: dict[str, Any]) -> str:
    drivers = recommendation.get("drivers", [])
    if isinstance(drivers, list) and drivers:
        return "; ".join(str(item) for item in drivers[:3])
    return "Recommendation derived from current field/session signals under experimental advisory mapping."


def recommend_cognitive_architecture(context: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, read-only cognitive architecture recommendation."""

    ranked = score_cognitive_arch_candidates(context)
    top = ranked[0] if ranked else CandidateScore("Mediator", "pragmatist_consultative", 0.2, tuple())
    total = sum(max(item.score, 0.0) for item in ranked) or 1.0
    confidence = _clamp(top.score / total + 0.35, 0.35, 0.95)

    payload: dict[str, Any] = {
        "figure": top.figure,
        "archetype": top.archetype,
        "reason": "",
        "confidence": round(confidence, 6),
        "signals": {
            "observer_state": context.get("observer_state"),
            "self_alignment": context.get("self_alignment"),
            "information_density": context.get("information_density"),
            "entropy_load": context.get("entropy_load"),
            "emergence_pressure": context.get("emergence_pressure"),
            "coherence_current": context.get("coherence_current"),
            "distance_to_c_star": context.get("distance_to_c_star"),
            "c_star_proximity": context.get("c_star_proximity"),
            "drift_band": context.get("drift_band"),
        },
        "source": "phios.field_guided.experimental_prior.v1",
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
        "drivers": list(top.drivers),
        "candidates": [
            {
                "figure": item.figure,
                "archetype": item.archetype,
                "score": item.score,
                "drivers": list(item.drivers),
            }
            for item in ranked
        ],
    }
    payload["reason"] = explain_cognitive_arch_recommendation(payload)
    return payload
