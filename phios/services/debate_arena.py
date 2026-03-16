"""Experimental coherence-gated debate arena service."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.constants import BIO_VACUUM_TARGET, C_STAR_THEORETICAL, HUNTER_C_STATUS
from phios.core.session_layer import build_session_checkin_report
from phios.services.agent_memory import (
    get_agent_memory,
    get_agent_memory_coherence,
    list_recent_agent_deliberations,
    store_agent_deliberation,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_for_session(session_id: str) -> str:
    return f"debate_session_{session_id.strip() or 'unknown'}"


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


def summarize_debate_positions(positions: list[dict[str, object]]) -> dict[str, object]:
    stance_counts: dict[str, int] = {}
    best_idx = 0
    best_support = -1.0
    best_figure = ""
    best_claim = ""

    for idx, pos in enumerate(positions):
        stance = str(pos.get("stance", "unspecified")).strip() or "unspecified"
        stance_counts[stance] = stance_counts.get(stance, 0) + 1
        support = _as_float(pos.get("support", 0.0), 0.0)
        figure = str(pos.get("figure", f"position_{idx+1}"))
        claim = str(pos.get("claim", pos.get("position", "")))
        if support > best_support:
            best_support = support
            best_idx = idx
            best_figure = figure
            best_claim = claim

    if positions and best_support <= 0.0:
        first = positions[0]
        best_figure = str(first.get("figure", "position_1"))
        best_claim = str(first.get("claim", first.get("position", "")))
        best_idx = 0

    return {
        "positions_count": len(positions),
        "stance_counts": stance_counts,
        "leading_position_index": best_idx,
        "leading_figure": best_figure,
        "leading_claim": best_claim,
    }


def build_debate_context(
    *,
    adapter: PhiKernelCLIAdapter,
    session_id: str,
    round_index: int,
    positions: list[dict[str, object]],
    threshold: float | None,
) -> dict[str, object]:
    try:
        checkin = build_session_checkin_report(adapter)
        checkin_dict: dict[str, object] = checkin if isinstance(checkin, dict) else {}
        coherence_candidate = checkin_dict.get("coherence", {})
        coherence_obj: dict[str, object] = coherence_candidate if isinstance(coherence_candidate, dict) else {}
        current = _as_float(coherence_obj.get("C_current"), 0.5)
    except Exception:
        field = adapter.field() if hasattr(adapter, "field") else {}
        field_dict: dict[str, object] = field if isinstance(field, dict) else {}
        current = _as_float(field_dict.get("C_current"), 0.5)
    threshold_val = _as_float(threshold, C_STAR_THEORETICAL) if threshold is not None else C_STAR_THEORETICAL

    prior = get_agent_memory_coherence(_topic_for_session(session_id))
    traces_obj = prior.get("coherence_traces", [])
    traces = traces_obj if isinstance(traces_obj, list) else []
    prior_trace: list[float] = []
    if traces:
        latest = traces[0] if isinstance(traces[0], dict) else {}
        candidate = latest.get("coherence_trace") if isinstance(latest, dict) else []
        if isinstance(candidate, list):
            prior_trace = [float(v) for v in candidate if isinstance(v, (int, float))]

    coherence_trace = [*prior_trace, current]
    return {
        "generated_at": _utc_now_iso(),
        "session_id": session_id,
        "round": max(1, int(round_index)),
        "coherence": current,
        "threshold": float(threshold_val),
        "delta_to_threshold": float(threshold_val - current),
        "coherence_trace": coherence_trace,
        "positions": positions,
        "position_summary": summarize_debate_positions(positions),
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
        "source": "phios.debate_arena.v1",
    }


def evaluate_debate_coherence_gate(context: dict[str, object]) -> dict[str, object]:
    round_idx = int(_as_float(context.get("round", 1), 1.0))
    coherence = _as_float(context.get("coherence"), 0.5)
    threshold = _as_float(context.get("threshold"), C_STAR_THEORETICAL)
    trace_obj = context.get("coherence_trace", [])
    trace = [float(v) for v in trace_obj if isinstance(v, (int, float))] if isinstance(trace_obj, list) else []

    action = "continue"
    reason = "Coherence has not crossed threshold; continue deliberation rounds."

    if coherence >= threshold:
        action = "converged"
        reason = "Coherence crossed threshold near theoretical C*; crystallization criteria met."
    else:
        recent = trace[-3:] if len(trace) >= 3 else trace
        span = (max(recent) - min(recent)) if recent else 1.0
        if round_idx >= 3 and coherence < threshold and span <= 0.015:
            action = "deadlock"
            reason = "Coherence plateau detected across recent rounds below threshold; deadlock suggested."

    summary_obj = context.get("position_summary", {})
    summary: dict[str, object] = summary_obj if isinstance(summary_obj, dict) else {}
    positions_obj = context.get("positions", [])
    positions_list = positions_obj if isinstance(positions_obj, list) else []
    decision = {
        "winning_figure": summary.get("leading_figure", ""),
        "winning_claim": summary.get("leading_claim", ""),
        "dissent_record": [
            {
                "figure": str(pos.get("figure", "")),
                "stance": str(pos.get("stance", "unspecified")),
                "claim": str(pos.get("claim", pos.get("position", ""))),
            }
            for pos in positions_list
            if isinstance(pos, dict) and str(pos.get("figure", "")) != str(summary.get("leading_figure", ""))
        ],
    }

    return {
        "action": action,
        "reason": reason,
        "coherence": coherence,
        "threshold": threshold,
        "delta_to_threshold": float(threshold - coherence),
        "coherence_trace": trace,
        "coherence_trace_summary": {
            "points": len(trace),
            "min": min(trace) if trace else None,
            "max": max(trace) if trace else None,
            "last": trace[-1] if trace else None,
        },
        "round": round_idx,
        "crystallized_decision": decision,
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
        "generated_at": _utc_now_iso(),
    }


def persist_debate_outcome(*, session_id: str, gate_result: dict[str, object], positions: list[dict[str, object]]) -> dict[str, object]:
    topic = _topic_for_session(session_id)
    decision_obj = gate_result.get("crystallized_decision", {})
    decision: dict[str, object] = decision_obj if isinstance(decision_obj, dict) else {}
    winning_figure = str(decision.get("winning_figure", "")) or "undetermined"
    outcome = str(gate_result.get("action", "continue"))
    trace_obj = gate_result.get("coherence_trace", [])
    trace = [float(v) for v in trace_obj if isinstance(v, (int, float))] if isinstance(trace_obj, list) else []

    stored = store_agent_deliberation(
        topic=topic,
        positions=positions,
        outcome=outcome,
        winning_figure=winning_figure,
        coherence_trace=trace,
        tags=["debate", "coherence-gate", f"action:{outcome}"],
        metadata={
            "session_id": session_id,
            "gate_result": {
                "action": gate_result.get("action", "continue"),
                "reason": gate_result.get("reason", ""),
                "round": gate_result.get("round", 1),
            },
            "stored_via": "phios.services.debate_arena.persist_debate_outcome",
        },
    )
    return stored


def get_debate_session_resource(session_id: str) -> dict[str, object]:
    topic = _topic_for_session(session_id)
    memory = get_agent_memory(topic)
    return {
        "session_id": session_id,
        "topic": topic,
        **memory,
        "experimental": True,
    }


def list_recent_debates(limit: int = 10) -> dict[str, object]:
    recent = list_recent_agent_deliberations(limit=200)
    rows_obj = recent.get("deliberations", [])
    rows = rows_obj if isinstance(rows_obj, list) else []
    debates = [row for row in rows if isinstance(row, dict) and str(row.get("topic", "")).startswith("debate_session_")]
    debates = debates[: max(1, int(limit))]
    return {
        "debates": debates,
        "count": len(debates),
        "experimental": True,
        "generated_at": _utc_now_iso(),
    }
