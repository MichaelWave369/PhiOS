from __future__ import annotations

from phios.services.figure_fitness import (
    build_figure_fitness_report,
    record_figure_outcome,
    recommend_figure_for_task,
)


def test_record_path_and_report(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = record_figure_outcome(
        figure="Architect",
        skills=["planning", "review"],
        run_id="r1",
        pr_grade="A",
        merge_time_minutes=35.0,
        redispatch_count=0,
        issue_closed=True,
        coherence_at_completion=0.84,
        sector_at_dispatch="HG",
    )
    assert out["ok"] is True

    report = build_figure_fitness_report(top=5)
    assert report["total_records"] == 1
    assert report["figures_ranked"][0]["figure"] == "Architect"


def test_recommendation_path_with_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _ = record_figure_outcome(
        figure="Wayfinder",
        skills=["exploration", "planning"],
        run_id="r2",
        pr_grade="B+",
        merge_time_minutes=50.0,
        redispatch_count=1,
        issue_closed=True,
        coherence_at_completion=0.79,
        sector_at_dispatch="HB",
    )
    _ = record_figure_outcome(
        figure="Architect",
        skills=["planning", "refactor"],
        run_id="r3",
        pr_grade="A",
        merge_time_minutes=30.0,
        redispatch_count=0,
        issue_closed=True,
        coherence_at_completion=0.86,
        sector_at_dispatch="HB",
    )

    rec = recommend_figure_for_task(task_key="pr_review", sector="HB", required_skill="planning", min_coherence=0.8)
    assert rec["ok"] is True
    assert rec["recommended"]["figure"] == "Architect"


def test_sparse_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rec = recommend_figure_for_task(task_key="empty")
    assert rec["ok"] is True
    assert rec["recommended"] is None
