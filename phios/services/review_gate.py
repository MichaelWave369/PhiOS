"""Experimental coherence-gated adversarial architecture review service."""

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


def _review_topic(panel_id: str, pr_number: int | None) -> str:
    if pr_number is not None:
        return f"review_panel_{panel_id}_pr_{pr_number}"
    return f"review_panel_{panel_id}"


def summarize_reviewer_positions(
    reviewer_grades: list[dict[str, object]], reviewer_critiques: list[str]
) -> dict[str, object]:
    grades: list[float] = []
    labels: list[str] = []
    for idx, item in enumerate(reviewer_grades):
        if not isinstance(item, dict):
            continue
        grades.append(_as_float(item.get("grade", 0.0), 0.0))
        labels.append(str(item.get("reviewer", f"reviewer_{idx+1}")))

    avg = sum(grades) / len(grades) if grades else 0.0
    spread = (max(grades) - min(grades)) if grades else 0.0
    dissent = [
        {"reviewer": labels[i], "grade": grades[i]}
        for i in range(len(grades))
        if abs(grades[i] - avg) > 0.15
    ]

    critique_lengths = [len(c.strip()) for c in reviewer_critiques if isinstance(c, str)]
    critique_pressure = sum(1 for length in critique_lengths if length > 60)

    return {
        "reviewer_count": len(grades),
        "grade_average": round(avg, 6),
        "grade_spread": round(spread, 6),
        "dissent_count": len(dissent),
        "dissent_record": dissent,
        "critique_count": len([c for c in reviewer_critiques if isinstance(c, str)]),
        "critique_pressure": critique_pressure,
    }


def build_review_context(
    *,
    adapter: PhiKernelCLIAdapter,
    round_index: int,
    reviewer_grades: list[dict[str, object]],
    reviewer_critiques: list[str],
    panel_id: str,
    pr_number: int | None,
) -> dict[str, object]:
    try:
        checkin = build_session_checkin_report(adapter)
        checkin_dict: dict[str, object] = checkin if isinstance(checkin, dict) else {}
        coherence_obj = checkin_dict.get("coherence", {})
        cdict: dict[str, object] = coherence_obj if isinstance(coherence_obj, dict) else {}
        coherence = _as_float(cdict.get("C_current"), 0.5)
    except Exception:
        field = adapter.field() if hasattr(adapter, "field") else {}
        fdict: dict[str, object] = field if isinstance(field, dict) else {}
        coherence = _as_float(fdict.get("C_current"), 0.5)

    topic = _review_topic(panel_id, pr_number)
    prior = get_agent_memory_coherence(topic)
    traces_obj = prior.get("coherence_traces", [])
    traces = traces_obj if isinstance(traces_obj, list) else []
    prev_trace: list[float] = []
    if traces and isinstance(traces[0], dict):
        cobj = traces[0].get("coherence_trace")
        if isinstance(cobj, list):
            prev_trace = [float(v) for v in cobj if isinstance(v, (int, float))]

    summary = summarize_reviewer_positions(reviewer_grades, reviewer_critiques)
    return {
        "generated_at": _utc_now_iso(),
        "round": max(1, int(round_index)),
        "panel_id": panel_id,
        "pr_number": pr_number,
        "topic": topic,
        "coherence": coherence,
        "coherence_trace": [*prev_trace, coherence],
        "reviewer_grades": reviewer_grades,
        "reviewer_critiques": reviewer_critiques,
        "grade_summary": summary,
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
    }


def evaluate_review_coherence_gate(context: dict[str, object]) -> dict[str, object]:
    coherence = _as_float(context.get("coherence"), 0.5)
    round_idx = int(_as_float(context.get("round"), 1.0))
    grade_summary_obj = context.get("grade_summary", {})
    grade_summary: dict[str, object] = (
        grade_summary_obj if isinstance(grade_summary_obj, dict) else {}
    )
    spread = _as_float(grade_summary.get("grade_spread"), 1.0)
    critique_pressure = int(_as_float(grade_summary.get("critique_pressure"), 0.0))
    trace_obj = context.get("coherence_trace", [])
    trace = [float(v) for v in trace_obj if isinstance(v, (int, float))] if isinstance(trace_obj, list) else []

    action = "continue"
    reason = "Review should continue; coherence and reviewer spread not yet converged."

    if coherence >= 0.88 and spread <= 0.2:
        action = "converged"
        reason = "High coherence with narrow grade spread indicates converged review signal."
    elif spread >= 0.45 or critique_pressure >= 2:
        action = "mediate"
        reason = "High disagreement or critique pressure indicates mediator synthesis step is required."
    elif round_idx >= 3 and trace:
        recent = trace[-3:]
        if max(recent) - min(recent) < 0.02 and spread > 0.25:
            action = "mediate"
            reason = "Coherence plateau with unresolved reviewer spread indicates mediation needed."

    critiques_obj = context.get("reviewer_critiques", [])
    critiques = critiques_obj if isinstance(critiques_obj, list) else []
    return {
        "action": action,
        "reason": reason,
        "coherence": coherence,
        "round": round_idx,
        "grade_summary": grade_summary,
        "critique_summary": {
            "count": len([c for c in critiques if isinstance(c, str)]),
            "sample": [str(c) for c in critiques[:3] if isinstance(c, str)],
        },
        "coherence_trace": trace,
        "coherence_trace_summary": {
            "points": len(trace),
            "min": min(trace) if trace else None,
            "max": max(trace) if trace else None,
            "last": trace[-1] if trace else None,
        },
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
        "generated_at": _utc_now_iso(),
    }


def persist_review_outcome(
    *,
    panel_id: str,
    pr_number: int | None,
    gate_result: dict[str, object],
    reviewer_grades: list[dict[str, object]],
    reviewer_critiques: list[str],
    mediator_summary: str | None,
) -> dict[str, object]:
    topic = _review_topic(panel_id, pr_number)
    action = str(gate_result.get("action", "continue"))
    grades_positions: list[dict[str, object]] = [
        {
            "figure": str(g.get("reviewer", "reviewer")),
            "claim": str(g.get("claim", "review grade")),
            "stance": str(g.get("stance", "review")),
            "notes": f"grade={_as_float(g.get('grade', 0.0), 0.0):.3f}",
        }
        for g in reviewer_grades
        if isinstance(g, dict)
    ]
    trace_obj = gate_result.get("coherence_trace", [])
    trace = [float(v) for v in trace_obj if isinstance(v, (int, float))] if isinstance(trace_obj, list) else []

    return store_agent_deliberation(
        topic=topic,
        positions=grades_positions,
        outcome=action,
        winning_figure=("mediator" if action == "mediate" else "review_panel"),
        coherence_trace=trace,
        tags=["review", "adversarial", f"action:{action}"],
        metadata={
            "panel_id": panel_id,
            "pr_number": pr_number,
            "reviewer_grades": reviewer_grades,
            "reviewer_critiques": reviewer_critiques,
            "mediator_summary": mediator_summary or "",
            "gate_reason": gate_result.get("reason", ""),
            "stored_via": "phios.services.review_gate.persist_review_outcome",
        },
    )


def list_recent_reviews(limit: int = 10) -> dict[str, object]:
    recent = list_recent_agent_deliberations(limit=200)
    rows_obj = recent.get("deliberations", [])
    rows = rows_obj if isinstance(rows_obj, list) else []
    reviews = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("topic", "")).startswith("review_panel_")
    ]
    reviews = reviews[: max(1, int(limit))]
    return {
        "reviews": reviews,
        "count": len(reviews),
        "generated_at": _utc_now_iso(),
        "experimental": True,
    }


def get_review_panel_resource(panel_id: str, pr_number: int | None = None) -> dict[str, object]:
    topic = _review_topic(panel_id, pr_number)
    memory = get_agent_memory(topic)
    return {"panel_id": panel_id, "pr_number": pr_number, "topic": topic, **memory, "experimental": True}
