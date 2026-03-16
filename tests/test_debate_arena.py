from __future__ import annotations

from phios.services.debate_arena import (
    build_debate_context,
    evaluate_debate_coherence_gate,
)


class DummyAdapter:
    def status(self):
        return {"heart_state": "running", "anchor_verification_state": "verified"}

    def field(self):
        return {
            "C_current": 0.4,
            "distance_to_C_star": 0.4,
            "recommended_action": "stabilize",
            "field_band": "amber",
            "fragmentation_score": 0.2,
        }

    def capsule_list(self):
        return {"capsules": [1]}


def _positions() -> list[dict[str, object]]:
    return [
        {"figure": "Architect", "claim": "scope", "stance": "pro", "support": 0.9},
        {"figure": "Wayfinder", "claim": "explore", "stance": "con", "support": 0.4},
    ]


def test_debate_converged_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    class ConvergeAdapter(DummyAdapter):
        def field(self):
            out = super().field()
            out["C_current"] = 0.95
            out["distance_to_C_star"] = 0.0
            return out

    ctx = build_debate_context(adapter=ConvergeAdapter(), session_id="s1", round_index=2, positions=_positions(), threshold=0.9)
    gate = evaluate_debate_coherence_gate(ctx)
    assert gate["action"] == "converged"


def test_debate_continue_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = build_debate_context(adapter=DummyAdapter(), session_id="s2", round_index=1, positions=_positions(), threshold=0.9)
    gate = evaluate_debate_coherence_gate(ctx)
    assert gate["action"] == "continue"


def test_debate_deadlock_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    # seed prior nearly-flat coherence trace via multiple rounds
    for r in [1, 2, 3]:
        ctx = {
            "round": r,
            "coherence": 0.5,
            "threshold": 0.9,
            "coherence_trace": [0.5, 0.505, 0.504],
            "positions": _positions(),
            "position_summary": {"leading_figure": "Architect", "leading_claim": "scope"},
        }
        gate = evaluate_debate_coherence_gate(ctx)
    assert gate["action"] == "deadlock"


def test_threshold_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = build_debate_context(adapter=DummyAdapter(), session_id="s3", round_index=1, positions=_positions(), threshold=None)
    assert "threshold" in ctx
