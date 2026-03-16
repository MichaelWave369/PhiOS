from __future__ import annotations

from phios.services.cognitive_arch import (
    recommend_cognitive_architecture,
    score_cognitive_arch_candidates,
)


def _context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "observer_state": "grounded",
        "self_alignment": "re-centering",
        "information_density": "forming",
        "entropy_load": "moderate",
        "emergence_pressure": "steady",
        "drift_band": "green",
        "coherence_current": 0.7,
        "distance_to_c_star": 0.1,
        "c_star_proximity": 0.8,
    }
    base.update(overrides)
    return base


def test_high_emergence_pressure_path_prefers_wayfinder():
    rec = recommend_cognitive_architecture(_context(emergence_pressure="high", c_star_proximity=0.4))
    assert rec["figure"] == "Wayfinder"


def test_high_entropy_load_path_prefers_sentinel():
    rec = recommend_cognitive_architecture(_context(entropy_load="high", c_star_proximity=0.4))
    assert rec["figure"] == "Sentinel"


def test_high_self_alignment_path_prefers_architect():
    rec = recommend_cognitive_architecture(_context(self_alignment="aligned", c_star_proximity=0.4, emergence_pressure="steady"))
    assert rec["figure"] == "Architect"


def test_low_coherence_path_prefers_mediator():
    rec = recommend_cognitive_architecture(_context(coherence_current=0.4, drift_band="red", c_star_proximity=0.2))
    assert rec["figure"] == "Mediator"


def test_near_c_star_path_prefers_visionary():
    rec = recommend_cognitive_architecture(_context(c_star_proximity=0.97, coherence_current=0.81, emergence_pressure="steady"))
    assert rec["figure"] == "Visionary"


def test_scoring_is_deterministic_and_sorted():
    scores = score_cognitive_arch_candidates(_context(emergence_pressure="high", entropy_load="high"))
    assert len(scores) == 5
    assert scores[0].score >= scores[1].score
