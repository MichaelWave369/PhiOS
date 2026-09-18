from __future__ import annotations

import hashlib
from pathlib import Path

from phios.mandala import (
    AuthorityContext,
    Gate,
    GateReceipt,
    MandalaPacket,
    MandalaReceiptLedger,
    MandalaStatus,
    OriginKind,
    OriginRef,
    PerceptionReceipt,
)
from phios.mandala.receipts import receipt_meta

from .evidence import NativeEvidenceStore
from .models import AcuityStatus, ObservationResult

SUPPORTED_TRANSFORMS = (
    "strip_utf8_bom",
    "normalize_newlines",
)


class SomaPerceptionService:
    """North Gate service for bounded, provenance-preserving text perception."""

    def __init__(
        self,
        *,
        state_root: Path,
        ledger: MandalaReceiptLedger,
        task_id: str,
        authority: AuthorityContext,
    ) -> None:
        self.evidence = NativeEvidenceStore(state_root / "evidence" / "native")
        self.ledger = ledger
        self.task_id = task_id
        self.authority = authority

    @staticmethod
    def _apply_transform(text: str, transform: str) -> str:
        if transform == "strip_utf8_bom":
            return text.removeprefix("\ufeff")
        if transform == "normalize_newlines":
            return text.replace("\r\n", "\n").replace("\r", "\n")
        raise ValueError(f"unsupported perception transform: {transform}")

    def perceive_text(
        self,
        *,
        source_id: str,
        text: str,
        transforms: tuple[str, ...] = (),
        source_kind: OriginKind = OriginKind.HUMAN,
    ) -> ObservationResult:
        if not source_id.strip():
            raise ValueError("source_id must not be empty")

        native = self.evidence.put_text(text)
        packet = MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.PERCEPTION,
            origin=OriginRef(kind=source_kind, identifier=source_id),
            payload={
                "source_id": source_id,
                "media_type": native.media_type,
                "native_sha256": native.sha256,
            },
            authority=self.authority,
            evidence_refs=(native.evidence_ref,),
            claims=(
                {
                    "kind": "observation_request",
                    "source_id": source_id,
                    "epistemic_status": "observed_input",
                },
            ),
            allowed_destinations=(Gate.DELIBERATION, Gate.MEMORY),
        )

        gate_receipt = GateReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.ACCEPTED,
                produced_by="soma.perception_gate",
            ),
            gate=Gate.PERCEPTION,
            reason="native source admitted; no truth or action authority conferred",
            provenance_refs=(native.evidence_ref,),
            authority=packet.authority.to_dict(),
        )
        self.ledger.append(gate_receipt)

        unsupported = tuple(item for item in transforms if item not in SUPPORTED_TRANSFORMS)
        if unsupported:
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.text",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=native.evidence_ref,
                transforms=transforms,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    "unsupported_transform",
                    "native_evidence_preserved",
                    "enhancement_does_not_increase_authority",
                ),
                source_id=source_id,
                native_sha256=native.sha256,
                observation_sha256=None,
                native_preserved=True,
                media_type=native.media_type,
            )
            self.ledger.append(receipt)
            return ObservationResult(
                packet=packet,
                evidence=native,
                receipt=receipt,
                observation_sha256=None,
                observation_text=None,
            )

        observation = text
        changed = False
        for transform in transforms:
            updated = self._apply_transform(observation, transform)
            changed = changed or updated != observation
            observation = updated

        observation_sha256 = hashlib.sha256(observation.encode("utf-8")).hexdigest()
        limitations = [
            "observation_not_truth",
            "enhancement_does_not_increase_authority",
        ]

        if not text:
            status = MandalaStatus.DEGRADED
            acuity = AcuityStatus.DEGRADED
            limitations.append("empty_source")
        elif changed:
            status = MandalaStatus.ACCEPTED
            acuity = AcuityStatus.RECOVERED
        else:
            status = MandalaStatus.ACCEPTED
            acuity = AcuityStatus.NATIVE

        receipt = PerceptionReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="soma.text",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            native_evidence_ref=native.evidence_ref,
            transforms=transforms,
            acuity_status=acuity.value,
            limitations=tuple(limitations),
            source_id=source_id,
            native_sha256=native.sha256,
            observation_sha256=observation_sha256,
            native_preserved=True,
            media_type=native.media_type,
        )
        self.ledger.append(receipt)

        return ObservationResult(
            packet=packet,
            evidence=native,
            receipt=receipt,
            observation_sha256=observation_sha256,
            observation_text=observation,
        )
