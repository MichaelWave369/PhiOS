from __future__ import annotations

from phios.services.cognitive_atoms import (
    recommend_cognitive_atom_overrides,
    sector_to_cognitive_atoms,
)


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.81,
            "distance_to_C_star": 0.01,
            "geometry_balance": 0.8,
            "collector_activity": 0.75,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def test_mapping_geometry_balance_high_sets_deductive():
    out = sector_to_cognitive_atoms({"geometry_balance": 0.8})
    assert out["atom_overrides"]["epistemic_style"] == "deductive"


def test_mapping_geometry_balance_low_sets_abductive():
    out = sector_to_cognitive_atoms({"geometry_balance": 0.2})
    assert out["atom_overrides"]["epistemic_style"] == "abductive"


def test_mapping_vacuum_proximity_threshold_is_deterministic():
    near = sector_to_cognitive_atoms({"vacuum_proximity": 0.75})
    far = sector_to_cognitive_atoms({"vacuum_proximity": 0.74})
    assert near["atom_overrides"]["creativity_level"] == "inventive"
    assert far["atom_overrides"]["creativity_level"] == "convergent"


def test_mapping_entropy_high_sets_explicit_fail_loud():
    out = sector_to_cognitive_atoms({"observer_entropy": 0.8})
    assert out["atom_overrides"]["uncertainty_handling"] == "explicit"
    assert out["atom_overrides"]["error_posture"] == "fail_loud"


def test_mapping_collector_mirror_emotion_paths():
    out = sector_to_cognitive_atoms(
        {
            "collector_activity": 0.8,
            "mirror_alignment": 0.75,
            "emotion_field": 0.8,
        }
    )
    assert out["atom_overrides"]["cognitive_rhythm"] == "iterative"
    assert out["atom_overrides"]["collaboration_posture"] == "pair"
    assert out["atom_overrides"]["communication_style"] == "narrative"


def test_recommendation_sparse_fallback_is_present():
    out = recommend_cognitive_atom_overrides(DummyAdapter())
    assert "atom_overrides" in out
    assert out["experimental"] is True
