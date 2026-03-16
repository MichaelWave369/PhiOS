"""Program/learning rollup MCP resources (Phase 10, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.resources.collections import _as_rows, _rollup
from phios.services.visualizer import (
    list_visual_bloom_curricula,
    list_visual_bloom_journey_ensembles,
    list_visual_bloom_study_halls,
    list_visual_bloom_syllabi,
    list_visual_bloom_thematic_pathways,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_programs_curricula_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_curricula()),
        family="program_curricula",
        source="phios.services.visualizer.list_visual_bloom_curricula",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_programs_study_halls_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_study_halls()),
        family="program_study_halls",
        source="phios.services.visualizer.list_visual_bloom_study_halls",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_programs_thematic_pathways_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_thematic_pathways()),
        family="program_thematic_pathways",
        source="phios.services.visualizer.list_visual_bloom_thematic_pathways",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_programs_syllabi_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_syllabi()),
        family="program_syllabi",
        source="phios.services.visualizer.list_visual_bloom_syllabi",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_programs_journey_ensembles_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_journey_ensembles()),
        family="program_journey_ensembles",
        source="phios.services.visualizer.list_visual_bloom_journey_ensembles",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload
