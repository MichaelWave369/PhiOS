"""Capstone / collection-family rollup MCP resources (Phase 11, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.resources.collections import _as_rows, _rollup
from phios.services.visualizer import (
    list_visual_bloom_atlas_cohorts,
    list_visual_bloom_dossiers,
    list_visual_bloom_field_libraries,
    list_visual_bloom_storyboards,
    list_visual_bloom_syllabi,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_capstones_syllabi_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_syllabi()),
        family="capstone_syllabi",
        source="phios.services.visualizer.list_visual_bloom_syllabi",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_capstones_atlas_cohorts_rollup_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_atlas_cohorts()),
        family="capstone_atlas_cohorts",
        source="phios.services.visualizer.list_visual_bloom_atlas_cohorts",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_capstones_field_libraries_rollup_family_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_field_libraries()),
        family="capstone_field_libraries",
        source="phios.services.visualizer.list_visual_bloom_field_libraries",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_capstones_dossiers_rollup_family_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_dossiers()),
        family="capstone_dossiers",
        source="phios.services.visualizer.list_visual_bloom_dossiers",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload


def read_capstones_storyboards_rollup_family_resource() -> dict[str, object]:
    payload = _rollup(
        _as_rows(list_visual_bloom_storyboards()),
        family="capstone_storyboards",
        source="phios.services.visualizer.list_visual_bloom_storyboards",
    )
    payload.setdefault("generated_at", _utc_now_iso())
    return payload
