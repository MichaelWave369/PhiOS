from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

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

from .acquisition import BoundedTextFileAdapter, FileAcquisitionError, FileSourcePolicy
from .evidence import NativeEvidenceStore
from .models import AcuityStatus, FileObservationResult, NativeEvidence, ObservationResult

SUPPORTED_TRANSFORMS = (
    "strip_utf8_bom",
    "normalize_newlines",
)


class SomaPerceptionService:
    """North Gate service for bounded, provenance-preserving perception."""

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

    def _packet(
        self,
        *,
        source_id: str,
        source_kind: OriginKind,
        native: NativeEvidence | None,
        payload_extra: dict[str, Any] | None = None,
    ) -> MandalaPacket:
        payload: dict[str, Any] = {
            "source_id": source_id,
            **dict(payload_extra or {}),
        }
        evidence_refs: tuple[str, ...] = ()
        if native is not None:
            payload.update(
                {
                    "media_type": native.media_type,
                    "native_sha256": native.sha256,
                }
            )
            evidence_refs = (native.evidence_ref,)

        return MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.PERCEPTION,
            origin=OriginRef(kind=source_kind, identifier=source_id),
            payload=payload,
            authority=self.authority,
            evidence_refs=evidence_refs,
            claims=(
                {
                    "kind": "observation_request",
                    "source_id": source_id,
                    "epistemic_status": "observed_input",
                },
            ),
            allowed_destinations=(Gate.DELIBERATION, Gate.MEMORY),
        )

    def _gate_receipt(
        self,
        packet: MandalaPacket,
        *,
        status: MandalaStatus,
        reason: str,
    ) -> GateReceipt:
        receipt = GateReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="soma.perception_gate",
            ),
            gate=Gate.PERCEPTION,
            reason=reason,
            provenance_refs=packet.evidence_refs,
            authority=packet.authority.to_dict(),
        )
        self.ledger.append(receipt)
        return receipt

    def _derive_text(
        self,
        *,
        packet: MandalaPacket,
        native: NativeEvidence,
        text: str,
        transforms: tuple[str, ...],
        gate_receipt: GateReceipt,
        producer: str,
        source_id: str,
        acquisition_method: str,
        source_locator: str | None = None,
        source_root_ref: str | None = None,
    ) -> tuple[PerceptionReceipt, str | None, str | None]:
        unsupported = tuple(item for item in transforms if item not in SUPPORTED_TRANSFORMS)
        if unsupported:
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by=producer,
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
                acquisition_method=acquisition_method,
                acquisition_status="quarantined",
                source_locator=source_locator,
                source_root_ref=source_root_ref,
            )
            self.ledger.append(receipt)
            return receipt, None, None

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
                produced_by=producer,
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
            acquisition_method=acquisition_method,
            acquisition_status="accepted" if status is MandalaStatus.ACCEPTED else "degraded",
            source_locator=source_locator,
            source_root_ref=source_root_ref,
        )
        self.ledger.append(receipt)
        return receipt, observation, observation_sha256

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
        packet = self._packet(
            source_id=source_id,
            source_kind=source_kind,
            native=native,
        )
        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="native source admitted; no truth or action authority conferred",
        )
        receipt, observation, observation_sha256 = self._derive_text(
            packet=packet,
            native=native,
            text=text,
            transforms=transforms,
            gate_receipt=gate_receipt,
            producer="soma.text",
            source_id=source_id,
            acquisition_method="inline",
            source_locator=source_id,
        )
        return ObservationResult(
            packet=packet,
            evidence=native,
            receipt=receipt,
            observation_sha256=observation_sha256,
            observation_text=observation,
        )

    def perceive_file(
        self,
        *,
        source_root: Path,
        relative_path: str,
        transforms: tuple[str, ...] = (),
        max_bytes: int = 1_048_576,
    ) -> FileObservationResult:
        policy = FileSourcePolicy(root=source_root, max_bytes=max_bytes)
        root_ref = policy.root_ref()
        source_id = f"file:{relative_path}"

        try:
            adapter = BoundedTextFileAdapter(policy)
            acquired = adapter.acquire(relative_path)
        except (FileAcquisitionError, ValueError) as exc:
            code = exc.code if isinstance(exc, FileAcquisitionError) else "invalid_file_policy"
            packet = self._packet(
                source_id=source_id,
                source_kind=OriginKind.FILE,
                native=None,
                payload_extra={
                    "relative_path": relative_path,
                    "source_root_ref": root_ref,
                    "max_bytes": max_bytes,
                },
            )
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"file acquisition blocked: {code}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.file",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                transforms=transforms,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    code,
                    "native_evidence_unavailable",
                    "enhancement_does_not_increase_authority",
                ),
                source_id=source_id,
                native_sha256=None,
                observation_sha256=None,
                native_preserved=False,
                media_type=None,
                acquisition_method="bounded_file",
                acquisition_status="blocked",
                source_locator=relative_path,
                source_root_ref=root_ref,
            )
            self.ledger.append(receipt)
            return FileObservationResult(
                packet=packet,
                evidence=None,
                receipt=receipt,
                observation_sha256=None,
                observation_text=None,
                relative_path=relative_path,
                source_root_ref=root_ref,
            )

        native = self.evidence.put_bytes(
            acquired.data,
            media_type=acquired.media_type,
            suffix=acquired.suffix,
        )
        source_id = f"file:{acquired.relative_path}"
        packet = self._packet(
            source_id=source_id,
            source_kind=OriginKind.FILE,
            native=native,
            payload_extra={
                "relative_path": acquired.relative_path,
                "source_root_ref": root_ref,
                "max_bytes": max_bytes,
                "size_bytes": acquired.size_bytes,
            },
        )
        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="bounded file admitted and native bytes preserved",
        )

        try:
            text = acquired.data.decode("utf-8")
        except UnicodeDecodeError:
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.file",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=native.evidence_ref,
                transforms=transforms,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    "invalid_utf8",
                    "native_evidence_preserved",
                    "observation_not_interpreted",
                ),
                source_id=source_id,
                native_sha256=native.sha256,
                observation_sha256=None,
                native_preserved=True,
                media_type=native.media_type,
                acquisition_method="bounded_file",
                acquisition_status="quarantined",
                source_locator=acquired.relative_path,
                source_root_ref=root_ref,
            )
            self.ledger.append(receipt)
            return FileObservationResult(
                packet=packet,
                evidence=native,
                receipt=receipt,
                observation_sha256=None,
                observation_text=None,
                relative_path=acquired.relative_path,
                source_root_ref=root_ref,
            )

        receipt, observation, observation_sha256 = self._derive_text(
            packet=packet,
            native=native,
            text=text,
            transforms=transforms,
            gate_receipt=gate_receipt,
            producer="soma.file",
            source_id=source_id,
            acquisition_method="bounded_file",
            source_locator=acquired.relative_path,
            source_root_ref=root_ref,
        )
        return FileObservationResult(
            packet=packet,
            evidence=native,
            receipt=receipt,
            observation_sha256=observation_sha256,
            observation_text=observation,
            relative_path=acquired.relative_path,
            source_root_ref=root_ref,
        )
