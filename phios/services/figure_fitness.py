"""Experimental local-first figure fitness tracking service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from phios.core.constants import BIO_VACUUM_TARGET, C_STAR_THEORETICAL, HUNTER_C_STATUS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "figure"




def _as_float(value: object, default: float = 0.0) -> float:
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


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _records_path() -> Path:
    return Path.home() / ".phios" / "journal" / "visual_bloom" / "narratives" / "figure_fitness_records.json"


def _load_records_doc() -> dict[str, object]:
    path = _records_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if not isinstance(data.get("figure_outcomes"), list):
                    data["figure_outcomes"] = []
                return data
        except Exception:
            pass
    return {
        "name": "figure_fitness_records",
        "title": "Figure Fitness Records",
        "summary": "Experimental local-first figure outcome archive.",
        "collection": "agents",
        "tags": ["figure-fitness", "experimental", "local-first"],
        "figure_outcomes": [],
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_vacuum_target": BIO_VACUUM_TARGET,
            "hunter_c_status": HUNTER_C_STATUS,
        },
        "experimental": True,
    }


def _save_records_doc(doc: dict[str, object]) -> None:
    path = _records_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = _utc_now_iso()
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _grade_score(pr_grade: str) -> float:
    lookup = {
        "a+": 1.0,
        "a": 0.95,
        "a-": 0.9,
        "b+": 0.82,
        "b": 0.75,
        "b-": 0.68,
        "c+": 0.6,
        "c": 0.52,
        "c-": 0.45,
        "d": 0.3,
        "f": 0.1,
    }
    return lookup.get(pr_grade.strip().lower(), 0.5)


def _normalize_skills(skills: list[str] | list[object]) -> list[str]:
    return [str(skill).strip().lower() for skill in skills if str(skill).strip()]


def _record_narrative_ref(figure: str) -> dict[str, object]:
    slug = _slugify(figure)
    return {
        "narrative_name": "figure_fitness_records",
        "resource_uri": f"phios://figures/fitness/{slug}",
        "experimental": True,
        "source": "phios.observatory.narratives",
    }


def record_figure_outcome(
    *,
    figure: str,
    skills: list[str] | list[object],
    run_id: str,
    pr_grade: str,
    merge_time_minutes: float,
    redispatch_count: int,
    issue_closed: bool,
    coherence_at_completion: float,
    sector_at_dispatch: str,
    timestamp: str | None = None,
) -> dict[str, object]:
    if not figure.strip():
        return {"ok": False, "error_code": "INVALID_FIGURE", "reason": "figure is required"}

    doc = _load_records_doc()
    raw_records = doc.get("figure_outcomes", [])
    records = raw_records if isinstance(raw_records, list) else []

    record = {
        "record_id": f"f{len(records):05d}",
        "figure": figure.strip(),
        "skills": _normalize_skills(skills),
        "run_id": run_id.strip(),
        "pr_grade": pr_grade.strip(),
        "pr_grade_score": _grade_score(pr_grade),
        "merge_time_minutes": float(merge_time_minutes),
        "redispatch_count": max(0, int(redispatch_count)),
        "issue_closed": bool(issue_closed),
        "coherence_at_completion": float(coherence_at_completion),
        "sector_at_dispatch": sector_at_dispatch.strip() or "unknown",
        "timestamp": timestamp or _utc_now_iso(),
        "experimental": True,
        "framing": {
            "c_star_theoretical": C_STAR_THEORETICAL,
            "bio_vacuum_target": BIO_VACUUM_TARGET,
            "hunter_c_status": HUNTER_C_STATUS,
        },
    }
    records.append(record)
    doc["figure_outcomes"] = records
    _save_records_doc(doc)

    return {
        "ok": True,
        "stored": True,
        "record_id": record["record_id"],
        "figure": str(record["figure"]),
        "timestamp": record["timestamp"],
        "narrative_ref": _record_narrative_ref(str(record["figure"])),
        "experimental": True,
    }


def list_figure_fitness_records(
    *,
    figure: str | None = None,
    sector: str | None = None,
    limit: int = 200,
) -> dict[str, object]:
    doc = _load_records_doc()
    raw_records = doc.get("figure_outcomes", [])
    records = [r for r in raw_records if isinstance(r, dict)] if isinstance(raw_records, list) else []

    if figure:
        records = [r for r in records if str(r.get("figure", "")).lower() == figure.lower()]
    if sector:
        records = [r for r in records if str(r.get("sector_at_dispatch", "")).lower() == sector.lower()]

    records = sorted(records, key=lambda r: str(r.get("timestamp", "")), reverse=True)[: max(1, int(limit))]
    return {
        "records": records,
        "count": len(records),
        "generated_at": _utc_now_iso(),
        "experimental": True,
    }


def _aggregate_figure_metrics(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for rec in records:
        figure = str(rec.get("figure", "unknown"))
        grouped.setdefault(figure, []).append(rec)

    aggregates: list[dict[str, object]] = []
    for figure, items in grouped.items():
        total = len(items)
        grade_scores = [_as_float(r.get("pr_grade_score"), 0.5) for r in items]
        merge_times = [_as_float(r.get("merge_time_minutes"), 0.0) for r in items]
        coherence_vals = [_as_float(r.get("coherence_at_completion"), 0.0) for r in items]
        redispatches = [_as_int(r.get("redispatch_count"), 0) for r in items]
        close_flags = [bool(r.get("issue_closed", False)) for r in items]

        grade_success_rate = sum(1 for g in grade_scores if g >= 0.75) / total if total else 0.0
        avg_merge_time = sum(merge_times) / total if total else 0.0
        avg_coherence = sum(coherence_vals) / total if total else 0.0
        redispatch_rate = sum(redispatches) / total if total else 0.0
        close_rate = sum(1 for c in close_flags if c) / total if total else 0.0

        fitness_score = (
            0.35 * grade_success_rate
            + 0.25 * close_rate
            + 0.20 * avg_coherence
            + 0.10 * (1.0 / (1.0 + max(avg_merge_time, 0.0) / 120.0))
            + 0.10 * (1.0 / (1.0 + max(redispatch_rate, 0.0)))
        )

        aggregates.append(
            {
                "figure": figure,
                "records": total,
                "grade_success_rate": round(grade_success_rate, 6),
                "avg_merge_time_minutes": round(avg_merge_time, 6),
                "avg_coherence": round(avg_coherence, 6),
                "redispatch_rate": round(redispatch_rate, 6),
                "close_rate": round(close_rate, 6),
                "fitness_score": round(fitness_score, 6),
            }
        )

    return sorted(aggregates, key=lambda row: _as_float(row.get("fitness_score"), 0.0), reverse=True)


def build_figure_fitness_report(
    *,
    figure: str | None = None,
    sector: str | None = None,
    top: int = 10,
) -> dict[str, object]:
    listed = list_figure_fitness_records(figure=figure, sector=sector, limit=1000)
    records_obj = listed.get("records", [])
    records = records_obj if isinstance(records_obj, list) else []
    aggregates = _aggregate_figure_metrics([r for r in records if isinstance(r, dict)])
    top_rows = aggregates[: max(1, int(top))]

    return {
        "filters": {"figure": figure, "sector": sector, "top": max(1, int(top))},
        "total_records": len(records),
        "figures_ranked": top_rows,
        "generated_at": _utc_now_iso(),
        "experimental": True,
        "c_star_theoretical": C_STAR_THEORETICAL,
        "bio_vacuum_target": BIO_VACUUM_TARGET,
        "hunter_c_status": HUNTER_C_STATUS,
    }


def recommend_figure_for_task(
    *,
    task_key: str,
    sector: str | None = None,
    required_skill: str | None = None,
    min_coherence: float | None = None,
) -> dict[str, object]:
    report = build_figure_fitness_report(sector=sector, top=100)
    ranked_obj = report.get("figures_ranked", [])
    ranked = [r for r in ranked_obj if isinstance(r, dict)] if isinstance(ranked_obj, list) else []

    records_obj = list_figure_fitness_records(sector=sector, limit=1000).get("records", [])
    records = [r for r in records_obj if isinstance(r, dict)] if isinstance(records_obj, list) else []

    filtered: list[dict[str, object]] = []
    for row in ranked:
        figure = str(row.get("figure", ""))
        figure_records = [r for r in records if str(r.get("figure", "")).lower() == figure.lower()]

        if required_skill:
            required = required_skill.strip().lower()
            if not any(required in [str(s).lower() for s in r.get("skills", []) if isinstance(r.get("skills", []), list)] for r in figure_records):
                continue

        if min_coherence is not None:
            avg_coherence = _as_float(row.get("avg_coherence"), 0.0)
            if avg_coherence < float(min_coherence):
                continue

        filtered.append(row)

    chosen = filtered[0] if filtered else None
    if not chosen:
        return {
            "ok": True,
            "task_key": task_key,
            "recommended": None,
            "reason": "No figure satisfies current filters; insufficient or non-matching records.",
            "confidence": 0.0,
            "metrics_used": {
                "sector": sector,
                "required_skill": required_skill,
                "min_coherence": min_coherence,
                "records_considered": len(records),
            },
            "experimental": True,
        }

    fitness_score = _as_float(chosen.get("fitness_score"), 0.0)
    confidence = min(0.95, 0.55 + fitness_score * 0.4)
    return {
        "ok": True,
        "task_key": task_key,
        "recommended": {
            "figure": chosen.get("figure"),
            "fitness_score": fitness_score,
            "grade_success_rate": chosen.get("grade_success_rate"),
            "avg_merge_time_minutes": chosen.get("avg_merge_time_minutes"),
            "avg_coherence": chosen.get("avg_coherence"),
            "redispatch_rate": chosen.get("redispatch_rate"),
            "close_rate": chosen.get("close_rate"),
        },
        "reason": "Top ranked figure selected from deterministic fitness metrics.",
        "confidence": round(confidence, 6),
        "metrics_used": {
            "sector": sector,
            "required_skill": required_skill,
            "min_coherence": min_coherence,
            "records_considered": len(records),
        },
        "experimental": True,
    }


def summarize_figure_fitness_landscape(*, top: int = 10, sector: str | None = None) -> dict[str, object]:
    report = build_figure_fitness_report(sector=sector, top=top)
    ranked_obj = report.get("figures_ranked", [])
    ranked = ranked_obj if isinstance(ranked_obj, list) else []
    return {
        "summary": {
            "figures_tracked": len(ranked),
            "best_figure": ranked[0].get("figure") if ranked else None,
            "best_fitness_score": ranked[0].get("fitness_score") if ranked else None,
            "sector_filter": sector,
        },
        "report": report,
        "generated_at": _utc_now_iso(),
        "experimental": True,
    }
