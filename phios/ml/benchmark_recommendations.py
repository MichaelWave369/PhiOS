"""Local exploratory benchmarking for recommendation strategies.

This tooling is experimental and intended for local comparison only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _topk_ids(rows: list[dict[str, object]], k: int) -> list[str]:
    return [str(r.get("id", "")) for r in rows[: max(1, k)] if str(r.get("id", ""))]


def benchmark_recommendation_strategies(
    *,
    target_refs: list[str],
    strategies: list[str],
    recommender: Callable[[str, str, int], list[dict[str, object]]],
    top_k: int = 5,
) -> dict[str, object]:
    """Compare strategies by top-k overlap and diversity summary."""
    if not target_refs:
        return {"targets": 0, "results": [], "summary": {}}

    per_target: list[dict[str, object]] = []
    overlap_total = 0.0
    pair_count = 0
    diversity_totals: dict[str, int] = {s: 0 for s in strategies}

    for target in target_refs:
        strat_rows: dict[str, list[dict[str, object]]] = {
            s: recommender(target, s, top_k) for s in strategies
        }
        strat_ids = {s: set(_topk_ids(rows, top_k)) for s, rows in strat_rows.items()}
        for s in strategies:
            diversity_totals[s] += len(strat_ids[s])

        local_overlap: dict[str, float] = {}
        for i, a in enumerate(strategies):
            for b in strategies[i + 1 :]:
                ua = strat_ids[a]
                ub = strat_ids[b]
                union = len(ua | ub)
                score = (len(ua & ub) / union) if union else 1.0
                local_overlap[f"{a}__vs__{b}"] = score
                overlap_total += score
                pair_count += 1

        per_target.append({
            "target_ref": target,
            "strategies": {k: v for k, v in strat_rows.items()},
            "overlap": local_overlap,
        })

    summary = {
        "avg_pairwise_topk_overlap": (overlap_total / pair_count) if pair_count else 1.0,
        "avg_unique_recs_per_strategy": {
            s: diversity_totals[s] / len(target_refs) for s in strategies
        },
    }
    return {
        "targets": len(target_refs),
        "top_k": top_k,
        "strategies": strategies,
        "results": per_target,
        "summary": summary,
        "status": "experimental_exploratory_benchmark",
    }


def write_benchmark_summary(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
