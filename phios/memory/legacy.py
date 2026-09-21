from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from phios.mandala import (
    ExactnessClass,
    TransformationLineageBuilder,
    TransformationLineageReceipt,
)

from .models import MemoryRecord
from .validation import require_utc_timestamp, sha256_json, strict_canonical_json


@dataclass(frozen=True, kw_only=True)
class LegacyImportItem:
    record: MemoryRecord
    operation_id: str
    transformation_lineage: tuple[TransformationLineageReceipt, ...]


@dataclass(frozen=True, kw_only=True)
class LegacyImportPlan:
    source_path: str
    source_sha256: str
    items: tuple[LegacyImportItem, ...]

    @property
    def count(self) -> int:
        return len(self.items)


def plan_legacy_agent_memory_import(
    path: Path,
    *,
    scope_id: str,
    classification: str,
    retention_policy_id: str,
    max_bytes: int = 4 * 1024 * 1024,
) -> LegacyImportPlan:
    source = path.expanduser().resolve()
    raw = source.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("legacy memory file exceeds configured import bound")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("legacy memory file is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("legacy memory root must be an object")
    deliberations = payload.get("agent_deliberations")
    if not isinstance(deliberations, list):
        raise ValueError("legacy memory has no agent_deliberations array")

    items: list[LegacyImportItem] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(deliberations):
        if not isinstance(item, dict):
            raise ValueError(f"legacy deliberation {index} must be an object")
        created_at_raw = item.get("created_at")
        if not isinstance(created_at_raw, str):
            raise ValueError(f"legacy deliberation {index} has no created_at")
        created_at = require_utc_timestamp(created_at_raw, "created_at")
        item_digest = sha256_json(item)
        legacy_id = str(item.get("deliberation_id", f"index-{index}")).strip() or f"index-{index}"
        record_id = f"legacy-agent-{source_sha256[:16]}-{item_digest[:16]}"
        if record_id in seen_ids:
            raise ValueError("legacy import contains duplicate canonical record identity")
        seen_ids.add(record_id)
        source_id = f"legacy-agent-memory:{source_sha256}:{legacy_id}"
        canonical_text = strict_canonical_json(item)
        content_sha256 = hashlib.sha256(
            canonical_text.encode("utf-8")
        ).hexdigest()
        lineage = TransformationLineageBuilder().build(
            transform_id="memory.legacy.extract_deliberation",
            transform_version="v0.1",
            source_refs=(f"legacy-file-sha256:{source_sha256}",),
            source_sha256s=(source_sha256,),
            output_ref=f"memory-content:sha256:{content_sha256}",
            output_sha256=content_sha256,
            parameters={
                "legacy_id": legacy_id,
                "index": index,
                "serialization": "strict_canonical_json",
            },
            requested_exactness=ExactnessClass.LOSSY_DERIVED,
            added_taints=(
                "canonicalized_representation",
                "extracted_subset",
            ),
            information_loss_possible=True,
            semantic_inference=False,
            limitations=(
                "legacy_file_context_outside_deliberation_not_in_output",
                "source_file_preserved",
            ),
        )
        record = MemoryRecord.build(
            record_id=record_id,
            revision=1,
            source_id=source_id,
            source_kind="file",
            provenance_refs=(
                f"legacy-file-sha256:{source_sha256}",
                f"legacy-deliberation:{legacy_id}",
            ),
            created_at=created_at,
            scope_id=scope_id,
            classification=classification,
            retention_policy_id=retention_policy_id,
            expires_at=None,
            epistemic_kind="derived",
            derived_from=(f"legacy-file-sha256:{source_sha256}",),
            exactness_class=lineage.exactness_class.value,
            transformation_lineage_sha256s=(lineage.receipt_sha256,),
            taint_labels=lineage.effective_taints,
            contradicts=(),
            text=canonical_text,
        )
        operation_id = f"legacy-import:{source_sha256}:{item_digest}"
        items.append(
            LegacyImportItem(
                record=record,
                operation_id=operation_id,
                transformation_lineage=(lineage,),
            )
        )
    return LegacyImportPlan(
        source_path=str(source),
        source_sha256=source_sha256,
        items=tuple(items),
    )
