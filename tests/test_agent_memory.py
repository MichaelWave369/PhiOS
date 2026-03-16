from __future__ import annotations

from phios.services.agent_memory import (
    get_agent_memory,
    get_agent_memory_coherence,
    list_recent_agent_deliberations,
    store_agent_deliberation,
)


def _positions() -> list[dict[str, object]]:
    return [
        {"figure": "Architect", "claim": "stabilize scope", "stance": "pro"},
        {"figure": "Wayfinder", "claim": "explore alternatives", "stance": "con"},
    ]


def test_store_and_get_agent_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = store_agent_deliberation(
        topic="alignment",
        positions=_positions(),
        outcome="consensus",
        winning_figure="Architect",
        coherence_trace=[0.44, 0.51, 0.62],
        tags=["debate", "alignment"],
    )
    assert out["ok"] is True

    mem = get_agent_memory("alignment")
    assert mem["found"] is True
    assert mem["count"] == 1
    assert mem["deliberations"][0]["winning_figure"] == "Architect"


def test_coherence_projection(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    store_agent_deliberation(
        topic="routing",
        positions=_positions(),
        outcome="pilot",
        winning_figure="Wayfinder",
        coherence_trace=[0.3, 0.45],
        tags=["routing"],
    )
    out = get_agent_memory_coherence("routing")
    assert out["found"] is True
    assert out["count"] == 1
    assert out["coherence_traces"][0]["coherence_trace"] == [0.3, 0.45]


def test_recent_deliberations_and_sparse(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    sparse = get_agent_memory("unknown")
    assert sparse["found"] is False
    assert sparse["count"] == 0

    store_agent_deliberation(
        topic="topic-a",
        positions=_positions(),
        outcome="hold",
        winning_figure="Mediator",
        coherence_trace=[0.2],
        tags=["a"],
    )
    recent = list_recent_agent_deliberations(limit=10)
    assert recent["count"] >= 1
