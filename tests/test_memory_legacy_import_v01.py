import json
from pathlib import Path

import pytest

from phios.mandala import ExactnessClass
from phios.memory import MemoryAccessPolicy, MemoryPolicyRule
from phios.memory.config import MemoryRuntimeConfig
from phios.memory.legacy import plan_legacy_agent_memory_import
from phios.memory.operator import MemoryOperatorRuntime


def _legacy_file(path: Path) -> Path:
    payload = {
        "agent_deliberations": [
            {
                "deliberation_id": "d0001",
                "topic": "routing",
                "positions": [{"figure": "A", "claim": "use local", "stance": "support"}],
                "outcome": "local",
                "winning_figure": "A",
                "coherence_trace": [0.8, 0.9],
                "created_at": "2026-09-20T20:00:00+00:00",
                "experimental": True,
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _config() -> MemoryRuntimeConfig:
    return MemoryRuntimeConfig.from_mapping(
        {
            "enabled": True,
            "principal_id": "operator",
            "scopes": ["private"],
            "classifications": ["operator"],
            "retention_policy_id": "retain",
        }
    )


def test_legacy_plan_is_deterministic_and_marks_content_derived(tmp_path: Path) -> None:
    path = _legacy_file(tmp_path / "legacy.json")
    a = plan_legacy_agent_memory_import(
        path,
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
    )
    b = plan_legacy_agent_memory_import(
        path,
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
    )
    assert a.source_sha256 == b.source_sha256
    assert a.items[0].operation_id == b.items[0].operation_id
    assert a.items[0].record.record_id == b.items[0].record.record_id
    assert a.items[0].record.epistemic_kind == "derived"
    assert a.items[0].record.source_kind == "file"
    assert a.items[0].record.exactness_class == (
        ExactnessClass.LOSSY_DERIVED.value
    )
    assert a.items[0].record.transformation_lineage_sha256s == (
        a.items[0].transformation_lineage[0].receipt_sha256,
    )
    assert a.items[0].record.taint_labels == (
        "canonicalized_representation",
        "extracted_subset",
    )
    assert a.items[0].transformation_lineage[0].action_authority is False


def test_legacy_import_requires_distinct_import_and_write_authority(tmp_path: Path) -> None:
    plan = plan_legacy_agent_memory_import(
        _legacy_file(tmp_path / "legacy.json"),
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
    )
    runtime = MemoryOperatorRuntime(
        state_root=tmp_path / "memory",
        config=_config(),
        allowed_permissions=("memory.write",),
    )
    with pytest.raises(PermissionError, match="memory.import"):
        runtime.import_legacy(plan, task_id="task")


def test_explicit_legacy_import_publishes_and_becomes_readable(tmp_path: Path) -> None:
    plan = plan_legacy_agent_memory_import(
        _legacy_file(tmp_path / "legacy.json"),
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
    )
    runtime = MemoryOperatorRuntime(
        state_root=tmp_path / "memory",
        config=_config(),
        allowed_permissions=("memory.import", "memory.write", "memory.read"),
    )
    imported, record_ids = runtime.import_legacy(plan, task_id="task")
    assert imported == 1
    assert len(record_ids) == 1
    result = runtime.get(record_ids[0], task_id="task-read")
    assert result.status == "ok"
    assert result.record is not None
    assert '"topic":"routing"' in result.record.text
