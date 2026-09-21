from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

TRANSFORMATION_LINEAGE_RECEIPT_SCHEMA_VERSION = (
    "phios.transformation_lineage_receipt.v0.1"
)


class TransformationLineageError(ValueError):
    """Raised when transformation provenance would overstate exactness."""


class ExactnessClass(StrEnum):
    """Conservative exactness classes for derived artifacts."""

    BYTE_EXACT = "BYTE_EXACT"
    REVERSIBLE = "REVERSIBLE"
    NORMALIZED = "NORMALIZED"
    LOSSY_DERIVED = "LOSSY_DERIVED"
    INTERPRETIVE = "INTERPRETIVE"
    UNKNOWN = "UNKNOWN"


_EXACTNESS_STRENGTH = {
    ExactnessClass.BYTE_EXACT: 5,
    ExactnessClass.REVERSIBLE: 4,
    ExactnessClass.NORMALIZED: 3,
    ExactnessClass.LOSSY_DERIVED: 2,
    ExactnessClass.INTERPRETIVE: 1,
    ExactnessClass.UNKNOWN: 0,
}


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TransformationLineageError(
            "transformation lineage must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransformationLineageError(f"{label} must be non-empty")
    return value.strip()


def _require_sha256(value: str, label: str) -> str:
    normalized = _require_nonempty(value, label).lower()
    if len(normalized) != 64:
        raise TransformationLineageError(f"{label} must be a SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise TransformationLineageError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc
    return normalized


def _normalize_labels(values: Iterable[str], label: str) -> tuple[str, ...]:
    normalized = tuple(
        sorted({_require_nonempty(value, label) for value in values})
    )
    return normalized


def weakest_exactness(
    *classes: ExactnessClass,
) -> ExactnessClass:
    if not classes:
        return ExactnessClass.UNKNOWN
    return min(classes, key=lambda item: _EXACTNESS_STRENGTH[item])


@dataclass(frozen=True, slots=True)
class TransformationLineageReceipt:
    schema_version: str
    receipt_id: str
    transform_id: str
    transform_version: str
    source_refs: tuple[str, ...]
    source_sha256s: tuple[str, ...]
    output_ref: str
    output_sha256: str
    parameters_sha256: str
    parent_receipt_sha256s: tuple[str, ...]
    requested_exactness: ExactnessClass
    exactness_class: ExactnessClass
    source_taints: tuple[str, ...]
    added_taints: tuple[str, ...]
    effective_taints: tuple[str, ...]
    information_loss_possible: bool
    semantic_inference: bool
    limitations: tuple[str, ...]
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "transform_id": self.transform_id,
            "transform_version": self.transform_version,
            "source_refs": list(self.source_refs),
            "source_sha256s": list(self.source_sha256s),
            "output_ref": self.output_ref,
            "output_sha256": self.output_sha256,
            "parameters_sha256": self.parameters_sha256,
            "parent_receipt_sha256s": list(self.parent_receipt_sha256s),
            "requested_exactness": self.requested_exactness.value,
            "exactness_class": self.exactness_class.value,
            "source_taints": list(self.source_taints),
            "added_taints": list(self.added_taints),
            "effective_taints": list(self.effective_taints),
            "information_loss_possible": self.information_loss_possible,
            "semantic_inference": self.semantic_inference,
            "limitations": list(self.limitations),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


class TransformationLineageBuilder:
    """Build immutable lineage without allowing derived artifacts to gain exactness."""

    def build(
        self,
        *,
        transform_id: str,
        transform_version: str,
        source_refs: tuple[str, ...],
        source_sha256s: tuple[str, ...],
        output_ref: str,
        output_sha256: str,
        parameters: Mapping[str, object] | None,
        requested_exactness: ExactnessClass,
        source_taints: tuple[str, ...] = (),
        added_taints: tuple[str, ...] = (),
        parent_receipts: tuple[TransformationLineageReceipt, ...] = (),
        information_loss_possible: bool = False,
        semantic_inference: bool = False,
        limitations: tuple[str, ...] = (),
    ) -> TransformationLineageReceipt:
        transform_id = _require_nonempty(transform_id, "transform_id")
        transform_version = _require_nonempty(
            transform_version,
            "transform_version",
        )
        if not source_refs:
            raise TransformationLineageError("source_refs must not be empty")
        if len(source_refs) != len(source_sha256s):
            raise TransformationLineageError(
                "source_refs and source_sha256s must have equal length"
            )
        normalized_refs = tuple(
            _require_nonempty(value, "source_ref") for value in source_refs
        )
        normalized_source_sha = tuple(
            _require_sha256(value, "source_sha256") for value in source_sha256s
        )
        output_ref = _require_nonempty(output_ref, "output_ref")
        output_sha256 = _require_sha256(output_sha256, "output_sha256")
        parent_hashes = tuple(
            sorted(
                {
                    _require_sha256(
                        receipt.receipt_sha256,
                        "parent_receipt_sha256",
                    )
                    for receipt in parent_receipts
                }
            )
        )
        source_taints = _normalize_labels(source_taints, "source_taint")
        added_taints = _normalize_labels(added_taints, "added_taint")
        limitations = _normalize_labels(limitations, "limitation")

        if requested_exactness is ExactnessClass.BYTE_EXACT:
            if len(normalized_source_sha) != 1:
                raise TransformationLineageError(
                    "BYTE_EXACT requires exactly one source"
                )
            if normalized_source_sha[0] != output_sha256:
                raise TransformationLineageError(
                    "BYTE_EXACT requires identical source/output SHA-256"
                )
            if information_loss_possible or semantic_inference:
                raise TransformationLineageError(
                    "BYTE_EXACT cannot claim loss or semantic inference"
                )
        elif requested_exactness is ExactnessClass.REVERSIBLE:
            if information_loss_possible or semantic_inference:
                raise TransformationLineageError(
                    "REVERSIBLE cannot claim loss or semantic inference"
                )
        elif requested_exactness is ExactnessClass.NORMALIZED:
            if semantic_inference:
                raise TransformationLineageError(
                    "NORMALIZED cannot include semantic inference"
                )
        elif requested_exactness is ExactnessClass.LOSSY_DERIVED:
            if not information_loss_possible or semantic_inference:
                raise TransformationLineageError(
                    "LOSSY_DERIVED requires possible information loss and no semantic inference"
                )
        elif requested_exactness is ExactnessClass.INTERPRETIVE:
            if not semantic_inference:
                raise TransformationLineageError(
                    "INTERPRETIVE requires semantic inference"
                )

        inherited_exactness = tuple(
            receipt.exactness_class for receipt in parent_receipts
        )
        effective_exactness = weakest_exactness(
            requested_exactness,
            *inherited_exactness,
        )
        effective_taints = _normalize_labels(
            (
                *source_taints,
                *(
                    taint
                    for receipt in parent_receipts
                    for taint in receipt.effective_taints
                ),
                *added_taints,
            ),
            "effective_taint",
        )

        parameters_sha256 = _sha256(dict(parameters or {}))
        seed = {
            "schema_version": TRANSFORMATION_LINEAGE_RECEIPT_SCHEMA_VERSION,
            "transform_id": transform_id,
            "transform_version": transform_version,
            "source_refs": list(normalized_refs),
            "source_sha256s": list(normalized_source_sha),
            "output_ref": output_ref,
            "output_sha256": output_sha256,
            "parameters_sha256": parameters_sha256,
            "parent_receipt_sha256s": list(parent_hashes),
            "requested_exactness": requested_exactness.value,
            "exactness_class": effective_exactness.value,
            "effective_taints": list(effective_taints),
            "information_loss_possible": bool(information_loss_possible),
            "semantic_inference": bool(semantic_inference),
        }
        receipt_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "phios.transformation-lineage:" + _sha256(seed),
            )
        )
        body = {
            **seed,
            "receipt_id": receipt_id,
            "source_taints": list(source_taints),
            "added_taints": list(added_taints),
            "limitations": list(limitations),
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return TransformationLineageReceipt(
            schema_version=TRANSFORMATION_LINEAGE_RECEIPT_SCHEMA_VERSION,
            receipt_id=receipt_id,
            transform_id=transform_id,
            transform_version=transform_version,
            source_refs=normalized_refs,
            source_sha256s=normalized_source_sha,
            output_ref=output_ref,
            output_sha256=output_sha256,
            parameters_sha256=parameters_sha256,
            parent_receipt_sha256s=parent_hashes,
            requested_exactness=requested_exactness,
            exactness_class=effective_exactness,
            source_taints=source_taints,
            added_taints=added_taints,
            effective_taints=effective_taints,
            information_loss_possible=bool(information_loss_possible),
            semantic_inference=bool(semantic_inference),
            limitations=limitations,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_sha256(body),
        )
