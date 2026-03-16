from __future__ import annotations

import json

from phios.shell.phi_router import route_command
from phios.services.figure_fitness import record_figure_outcome


def test_shell_agents_figures_and_evolve(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _ = record_figure_outcome(
        figure="Architect",
        skills=["planning", "review"],
        run_id="r10",
        pr_grade="A",
        merge_time_minutes=25.0,
        redispatch_count=0,
        issue_closed=True,
        coherence_at_completion=0.88,
        sector_at_dispatch="HG",
    )

    out_figures, code_figures = route_command(["agents", "figures", "--top", "10", "--sector", "HG"])
    assert code_figures == 0
    payload_figures = json.loads(out_figures)
    assert "figures_ranked" in payload_figures

    out_evolve, code_evolve = route_command(["agents", "evolve", "--top", "5", "--task-key", "review"])
    assert code_evolve == 0
    payload_evolve = json.loads(out_evolve)
    assert payload_evolve["ok"] is True
    assert payload_evolve["advisory_only"] is True
