from __future__ import annotations

from phios.services.review_gate import build_review_context, evaluate_review_coherence_gate


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.7,
            "distance_to_C_star": 0.2,
            "recommended_action": "stabilize",
            "field_band": "amber",
            "fragmentation_score": 0.22,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def test_review_converged_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = {
        "round": 2,
        "coherence": 0.91,
        "grade_summary": {"grade_spread": 0.12, "critique_pressure": 0},
        "coherence_trace": [0.82, 0.91],
        "reviewer_critiques": ["looks good"],
    }
    out = evaluate_review_coherence_gate(ctx)
    assert out["action"] == "converged"


def test_review_mediate_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = {
        "round": 1,
        "coherence": 0.7,
        "grade_summary": {"grade_spread": 0.5, "critique_pressure": 3},
        "coherence_trace": [0.7],
        "reviewer_critiques": ["major concerns", "security risk"],
    }
    out = evaluate_review_coherence_gate(ctx)
    assert out["action"] == "mediate"


def test_review_continue_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    grades = [{"reviewer": "A", "grade": 0.7}, {"reviewer": "B", "grade": 0.8}]
    critiques = ["needs more tests"]
    ctx = build_review_context(
        adapter=DummyAdapter(),
        round_index=1,
        reviewer_grades=grades,
        reviewer_critiques=critiques,
        panel_id="p1",
        pr_number=12,
    )
    out = evaluate_review_coherence_gate(ctx)
    assert out["action"] in {"continue", "mediate", "converged"}
    assert "grade_summary" in out
