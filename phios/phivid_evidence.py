"""Validate PHIVid evidence envelopes without granting ledger admission.

This module consumes the portable envelope emitted by PHIVid. It verifies the
envelope digest and delegates every embedded EvidenceRef to PhiOS's canonical
EvidenceRef.from_dict() parser. Validation produces no ledger writes and no
operational, action, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phios.covenant.models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_sha256,
    require_text,
)
from phios.evidence_ref import EvidenceRef

PHIVID_ENVELOPE_SCHEMA_VERSION = "phivid.phios_evidence_envelope.v0.1"


@dataclass(frozen=True, slots=True)
class PHIVidEvidenceIntake:
    schema_version: str
    envelope_sha256: str
    source_receipt_sha256: str
    plan_id: str
    output_evidence_ref: str
    evidence_refs: tuple[EvidenceRef, ...]
    warnings: tuple[str, ...]
    ledger_admitted: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False


def _require_string_list(value: Any, label: str, *, maximum: int = 128) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} items")
    return tuple(require_text(item, f"{label} item", maximum=512) for item in value)


def validate_phivid_evidence_envelope(value: Any) -> PHIVidEvidenceIntake:
    data = expect_mapping(value, "PHIVid evidence envelope")
    expected = {
        "schema_version",
        "event_type",
        "produced_by",
        "source_receipt_sha256",
        "plan_id",
        "observed_at",
        "output_evidence_ref",
        "evidence_refs",
        "warnings",
        "operational_authority",
        "action_authority",
        "execution_authority",
        "envelope_sha256",
    }
    expect_exact_keys(data, expected, "PHIVid evidence envelope")

    schema_version = require_text(
        data["schema_version"],
        "schema_version",
        maximum=64,
    )
    if schema_version != PHIVID_ENVELOPE_SCHEMA_VERSION:
        raise ValueError(f"unsupported PHIVid envelope schema: {schema_version}")

    if require_text(data["event_type"], "event_type", maximum=64) != "phivid.render.verified":
        raise ValueError("unsupported PHIVid evidence event_type")
    if require_text(data["produced_by"], "produced_by", maximum=64) != "PHIVid":
        raise ValueError("PHIVid evidence envelope produced_by must be PHIVid")

    source_receipt_sha256 = require_sha256(
        data["source_receipt_sha256"],
        "source_receipt_sha256",
    )
    plan_id = require_text(data["plan_id"], "plan_id", maximum=256)
    require_text(data["observed_at"], "observed_at", maximum=64)
    output_evidence_ref = require_text(
        data["output_evidence_ref"],
        "output_evidence_ref",
        maximum=256,
    )

    for field in (
        "operational_authority",
        "action_authority",
        "execution_authority",
    ):
        if require_bool(data[field], field) is not False:
            raise ValueError(f"PHIVid evidence envelope cannot carry {field}")

    evidence_raw = data["evidence_refs"]
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise ValueError("evidence_refs must be a non-empty array")
    if len(evidence_raw) > 65:
        raise ValueError("evidence_refs exceeds 65 items")

    refs = tuple(EvidenceRef.from_dict(item) for item in evidence_raw)
    uri_order = tuple(ref.evidence_ref for ref in refs)
    if tuple(sorted(uri_order)) != uri_order:
        raise ValueError("PHIVid evidence_refs must be sorted by evidence_ref")
    if len(set(uri_order)) != len(uri_order):
        raise ValueError("PHIVid evidence_refs must not contain duplicates")

    output_refs = tuple(ref for ref in refs if ref.evidence_ref == output_evidence_ref)
    if len(output_refs) != 1:
        raise ValueError("output_evidence_ref must identify exactly one EvidenceRef")
    if output_refs[0].source_kind != "phivid.video.render":
        raise ValueError("output EvidenceRef must have source_kind phivid.video.render")

    warnings = _require_string_list(data["warnings"], "warnings")

    envelope_sha256 = require_sha256(data["envelope_sha256"], "envelope_sha256")
    body = dict(data)
    del body["envelope_sha256"]
    if canonical_sha256(body) != envelope_sha256:
        raise ValueError("PHIVid evidence envelope digest does not match canonical envelope")

    return PHIVidEvidenceIntake(
        schema_version=schema_version,
        envelope_sha256=envelope_sha256,
        source_receipt_sha256=source_receipt_sha256,
        plan_id=plan_id,
        output_evidence_ref=output_evidence_ref,
        evidence_refs=refs,
        warnings=warnings,
    )
