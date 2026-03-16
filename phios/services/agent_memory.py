"""Experimental local-first observatory-backed memory for agent deliberations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from phios.core.constants import BIO_VACUUM_TARGET, C_STAR_THEORETICAL, HUNTER_C_STATUS
from phios.services.visualizer import (
    VisualizerError,
    create_visual_bloom_narrative,
    list_visual_bloom_narratives,
    load_visual_bloom_narrative,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "topic"


def _normalize_positions(raw: list[dict[str, object]] | list[object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for idx, item in enumerate(raw):
        if isinstance(item, dict):
            out.append({
                "figure": str(item.get("figure", f"position_{idx+1}")),
                "claim": str(item.get("claim", item.get("position", ""))),
                "stance": str(item.get("stance", "undeclared")),
                "notes": str(item.get("notes", "")),
            })
        else:
            out.append({"figure": f"position_{idx+1}", "claim": str(item), "stance": "undeclared", "notes": ""})
    return out


def _topic_narrative_name(topic: str) -> str:
    return f"agent_memory_{_slugify(topic)}"


def _load_or_create_topic_doc(topic: str) -> tuple[str, dict[str, object]]:
    name = _topic_narrative_name(topic)
    try:
        doc = load_visual_bloom_narrative(name)
    except VisualizerError:
        create_visual_bloom_narrative(
            name=name,
            title=f"Agent Memory · {topic}",
            summary="Experimental local-first deliberation archive.",
            tags=["agent-memory", "experimental", "local-first"],
            collection="agents",
        )
        doc = load_visual_bloom_narrative(name)

    if not isinstance(doc.get("agent_deliberations"), list):
        doc["agent_deliberations"] = []
    return name, doc


def build_deliberation_narrative_ref(topic: str) -> dict[str, object]:
    name = _topic_narrative_name(topic)
    return {
        "narrative_name": name,
        "resource_uri": f"phios://agents/memory/{_slugify(topic)}",
        "experimental": True,
        "source": "phios.observatory.narratives",
    }


def store_agent_deliberation(
    *,
    topic: str,
    positions: list[dict[str, object]] | list[object],
    outcome: str,
    winning_figure: str,
    coherence_trace: list[float] | list[object],
    tags: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    if not topic.strip():
        return {"ok": False, "error_code": "INVALID_TOPIC", "reason": "topic is required"}

    normalized_positions = _normalize_positions(positions)
    trace = [float(v) for v in coherence_trace if isinstance(v, (int, float))]
    label_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

    name, doc = _load_or_create_topic_doc(topic)
    deliberations = doc.get("agent_deliberations")
    items = deliberations if isinstance(deliberations, list) else []

    record = {
        "deliberation_id": f"d{len(items):04d}",
        "topic": topic,
        "positions": normalized_positions,
        "outcome": outcome,
        "winning_figure": winning_figure,
        "coherence_trace": trace,
        "coherence_trace_summary": {
            "points": len(trace),
            "min": min(trace) if trace else None,
            "max": max(trace) if trace else None,
            "last": trace[-1] if trace else None,
        },
        "tags": label_tags,
        "created_at": _utc_now_iso(),
        "metadata": metadata or {},
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_vacuum_target": BIO_VACUUM_TARGET,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }
    items.append(record)
    doc["agent_deliberations"] = items

    entries = doc.get("entries")
    entry_items = entries if isinstance(entries, list) else []
    entry_items.append(
        {
            "entry_id": f"e{len(entry_items):03d}",
            "entry_type": "agent_deliberation",
            "title": f"Deliberation: {topic}",
            "note": json.dumps(
                {
                    "outcome": outcome,
                    "winning_figure": winning_figure,
                    "positions_count": len(normalized_positions),
                    "coherence_points": len(trace),
                    "tags": label_tags,
                }
            ),
            "created_at": record["created_at"],
            "tags": label_tags,
            "topic": topic,
        }
    )
    doc["entries"] = entry_items
    doc["updated_at"] = _utc_now_iso()

    # persist by replacing narrative file payload
    from pathlib import Path

    path = Path.home() / ".phios" / "journal" / "visual_bloom" / "narratives" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "topic": topic,
        "stored": True,
        "created_at": record["created_at"],
        "positions_count": len(normalized_positions),
        "tags": label_tags,
        "coherence_trace_summary": record["coherence_trace_summary"],
        "narrative_ref": build_deliberation_narrative_ref(topic),
        "experimental": True,
    }


def get_agent_memory(topic: str) -> dict[str, object]:
    name = _topic_narrative_name(topic)
    try:
        doc = load_visual_bloom_narrative(name)
    except VisualizerError:
        return {
            "topic": topic,
            "narrative_ref": build_deliberation_narrative_ref(topic),
            "deliberations": [],
            "count": 0,
            "found": False,
            "experimental": True,
        }

    delibs = doc.get("agent_deliberations")
    items = delibs if isinstance(delibs, list) else []
    return {
        "topic": topic,
        "narrative_ref": build_deliberation_narrative_ref(topic),
        "deliberations": items,
        "count": len(items),
        "found": True,
        "experimental": True,
    }


def get_agent_memory_coherence(topic: str) -> dict[str, object]:
    memory = get_agent_memory(topic)
    traces: list[dict[str, object]] = []
    deliberations_obj = memory.get("deliberations", [])
    deliberations = deliberations_obj if isinstance(deliberations_obj, list) else []
    for item in deliberations:
        if isinstance(item, dict):
            trace = item.get("coherence_trace")
            traces.append(
                {
                    "deliberation_id": item.get("deliberation_id", ""),
                    "created_at": item.get("created_at", ""),
                    "coherence_trace": trace if isinstance(trace, list) else [],
                    "summary": item.get("coherence_trace_summary", {}),
                }
            )

    return {
        "topic": topic,
        "narrative_ref": memory.get("narrative_ref"),
        "coherence_traces": traces,
        "count": len(traces),
        "found": bool(memory.get("found", False)),
        "experimental": True,
    }


def list_recent_agent_deliberations(limit: int = 10) -> dict[str, object]:
    rows = list_visual_bloom_narratives()[:200]
    events: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("narrative_name", ""))
        if not name.startswith("agent_memory_"):
            continue
        try:
            doc = load_visual_bloom_narrative(name)
        except VisualizerError:
            continue
        delibs = doc.get("agent_deliberations")
        for item in delibs if isinstance(delibs, list) else []:
            if isinstance(item, dict):
                events.append(
                    {
                        "topic": str(item.get("topic", "")),
                        "deliberation_id": str(item.get("deliberation_id", "")),
                        "created_at": str(item.get("created_at", "")),
                        "outcome": str(item.get("outcome", "")),
                        "winning_figure": str(item.get("winning_figure", "")),
                        "tags": item.get("tags", []),
                        "narrative_ref": build_deliberation_narrative_ref(str(item.get("topic", ""))),
                    }
                )
    events.sort(key=lambda e: str(e.get("created_at", "")), reverse=True)
    recent = events[: max(1, int(limit))]
    return {"deliberations": recent, "count": len(recent), "experimental": True}
