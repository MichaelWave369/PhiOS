from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from phios.mandala import (
    AuthorityContext,
    ExactnessClass,
    Gate,
    GateReceipt,
    MandalaPacket,
    MandalaReceiptLedger,
    MandalaStatus,
    OriginKind,
    OriginRef,
    OcrReceipt,
    PerceptionReceipt,
    TransformationLineageBuilder,
    TransformationLineageReceipt,
)
from phios.mandala.receipts import receipt_meta

from .acquisition import BoundedTextFileAdapter, FileAcquisitionError, FileSourcePolicy
from .evidence import NativeEvidenceStore
from .models import (
    AcuityStatus,
    FileObservationResult,
    NativeEvidence,
    ObservationResult,
    OcrObservationResult,
    ScreenBurstResult,
    ScreenEnhancementResult,
    ScreenObservationResult,
    ScreenRecoveryResult,
)
from .enhancement import (
    ScreenEnhancementError,
    ScreenEnhancementProvider,
    ScreenEnhancementSpec,
)
from .multishot import FrameSharpnessScorer, SharpnessScoreError
from .ocr import OcrEngineError, OcrProvider, OcrSpec, PNG_SIGNATURE
from .recovery import ScreenCrop, ScreenRecoveryError, ScreenRecoveryProvider
from .screen import CapturedFrame, ScreenCaptureError, ScreenCaptureProvider, ScreenRegion

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
        self.transformations = TransformationLineageBuilder()

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
    ) -> tuple[
        PerceptionReceipt,
        str | None,
        str | None,
        tuple[TransformationLineageReceipt, ...],
    ]:
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
            return receipt, None, None, ()

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

        exactness = (
            ExactnessClass.NORMALIZED
            if changed
            else ExactnessClass.BYTE_EXACT
        )
        lineage = self.transformations.build(
            transform_id=(
                "soma.text.normalize"
                if changed
                else "soma.text.identity"
            ),
            transform_version="v0.1",
            source_refs=(native.evidence_ref,),
            source_sha256s=(native.sha256,),
            output_ref=(
                f"observation:sha256:{observation_sha256}"
                if changed
                else native.evidence_ref
            ),
            output_sha256=observation_sha256,
            parameters={"transforms": list(transforms)},
            requested_exactness=exactness,
            added_taints=(
                ("normalized_representation",) if changed else ()
            ),
            information_loss_possible=changed,
            semantic_inference=False,
            limitations=("native_source_preserved",),
        )
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
            transformation_lineage_sha256s=(lineage.receipt_sha256,),
            exactness_class=lineage.exactness_class.value,
            taint_labels=lineage.effective_taints,
        )
        self.ledger.append(receipt)
        return receipt, observation, observation_sha256, (lineage,)

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
        receipt, observation, observation_sha256, lineage = self._derive_text(
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
            transformation_lineage=lineage,
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

        receipt, observation, observation_sha256, lineage = self._derive_text(
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
            transformation_lineage=lineage,
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


    def perceive_screen(
        self,
        *,
        region: ScreenRegion,
        provider: ScreenCaptureProvider,
        max_pixels: int = 8_294_400,
        reacquire_attempts: int = 1,
    ) -> ScreenObservationResult:
        permission = "perception.screen.capture"
        region_data = region.to_dict()
        source_id = (
            f"screen-region:{region.x},{region.y},"
            f"{region.width}x{region.height}"
        )
        packet = self._packet(
            source_id=source_id,
            source_kind=OriginKind.DEVICE,
            native=None,
            payload_extra={
                "capture_region": region_data,
                "capture_backend": provider.name,
                "max_pixels": max_pixels,
                "reacquire_attempts": reacquire_attempts,
            },
        )

        if not self.authority.allows(permission):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen capture blocked: missing explicit grant {permission}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    f"missing_grant:{permission}",
                    "native_evidence_unavailable",
                    "visibility_does_not_imply_permission",
                ),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_region",
                acquisition_status="blocked",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=provider.name,
                capture_attempts=0,
            )
            self.ledger.append(receipt)
            return ScreenObservationResult(
                packet=packet,
                evidence=None,
                receipt=receipt,
                region=region_data,
                capture_backend=provider.name,
                capture_attempts=0,
                observation_sha256=None,
            )

        try:
            region.validate(max_pixels=max_pixels)
            if reacquire_attempts < 0 or reacquire_attempts > 2:
                raise ScreenCaptureError(
                    "invalid_reacquire_attempts",
                    "reacquire_attempts must be between 0 and 2",
                )
        except ScreenCaptureError as exc:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen capture blocked: {exc.code}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    exc.code,
                    "native_evidence_unavailable",
                    "visibility_does_not_imply_permission",
                ),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_region",
                acquisition_status="blocked",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=provider.name,
                capture_attempts=0,
            )
            self.ledger.append(receipt)
            return ScreenObservationResult(
                packet=packet,
                evidence=None,
                receipt=receipt,
                region=region_data,
                capture_backend=provider.name,
                capture_attempts=0,
                observation_sha256=None,
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="explicit screen capture grant and region policy accepted",
        )

        total_attempts = 1 + reacquire_attempts
        last_code = "capture_failed"
        last_bad_frame: CapturedFrame | None = None
        attempts_used = 0

        for attempt in range(1, total_attempts + 1):
            attempts_used = attempt
            try:
                frame = provider.capture(region)
            except ScreenCaptureError as exc:
                last_code = exc.code
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                last_code = "capture_backend_error"
                continue

            if not frame.data:
                last_code = "empty_capture"
                continue
            if frame.media_type != "image/png" or frame.suffix.lower() != ".png":
                last_code = "unsupported_capture_format"
                last_bad_frame = frame
                continue
            if frame.width != region.width or frame.height != region.height:
                last_code = "capture_dimensions_mismatch"
                last_bad_frame = frame
                continue

            native = self.evidence.put_bytes(
                frame.data,
                media_type=frame.media_type,
                suffix=frame.suffix,
            )
            recovered = attempt > 1
            recovery_steps = ("reacquire_same_region",) if recovered else ()
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.ACCEPTED,
                    produced_by="soma.screen",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=native.evidence_ref,
                acuity_status=(
                    AcuityStatus.RECOVERED.value if recovered else AcuityStatus.NATIVE.value
                ),
                limitations=(
                    "observation_not_truth",
                    "screen_capture_contains_no_interpretation",
                    "enhancement_does_not_increase_authority",
                ),
                source_id=source_id,
                native_sha256=native.sha256,
                observation_sha256=native.sha256,
                native_preserved=True,
                media_type=native.media_type,
                acquisition_method="screen_region",
                acquisition_status="accepted",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=frame.backend,
                capture_attempts=attempt,
                recovery_steps=recovery_steps,
            )
            self.ledger.append(receipt)
            return ScreenObservationResult(
                packet=packet,
                evidence=native,
                receipt=receipt,
                region=region_data,
                capture_backend=frame.backend,
                capture_attempts=attempt,
                observation_sha256=native.sha256,
            )

        if last_bad_frame is not None:
            native = self.evidence.put_bytes(
                last_bad_frame.data,
                media_type=last_bad_frame.media_type,
                suffix=last_bad_frame.suffix,
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.screen",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=native.evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    last_code,
                    "native_evidence_preserved",
                    "screen_capture_not_interpreted",
                ),
                source_id=source_id,
                native_sha256=native.sha256,
                observation_sha256=None,
                native_preserved=True,
                media_type=native.media_type,
                acquisition_method="screen_region",
                acquisition_status="quarantined",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=last_bad_frame.backend,
                capture_attempts=attempts_used,
                recovery_steps=(
                    ("reacquire_same_region",) if attempts_used > 1 else ()
                ),
            )
            self.ledger.append(receipt)
            return ScreenObservationResult(
                packet=packet,
                evidence=native,
                receipt=receipt,
                region=region_data,
                capture_backend=last_bad_frame.backend,
                capture_attempts=attempts_used,
                observation_sha256=None,
            )

        receipt = PerceptionReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.DEGRADED,
                produced_by="soma.screen",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            native_evidence_ref=None,
            acuity_status=AcuityStatus.UNAVAILABLE.value,
            limitations=(
                last_code,
                "native_evidence_unavailable",
                "no_observation_fabricated",
            ),
            source_id=source_id,
            native_preserved=False,
            acquisition_method="screen_region",
            acquisition_status="unavailable",
            source_locator=source_id,
            capture_region=region_data,
            capture_backend=provider.name,
            capture_attempts=attempts_used,
            recovery_steps=(
                ("reacquire_same_region",) if attempts_used > 1 else ()
            ),
        )
        self.ledger.append(receipt)
        return ScreenObservationResult(
            packet=packet,
            evidence=None,
            receipt=receipt,
            region=region_data,
            capture_backend=provider.name,
            capture_attempts=attempts_used,
            observation_sha256=None,
        )


    def recover_screen_evidence(
        self,
        *,
        evidence_ref: str,
        provider: ScreenRecoveryProvider,
        crop: ScreenCrop | None = None,
        scale: int = 1,
        max_output_pixels: int = 16_777_216,
    ) -> ScreenRecoveryResult:
        permission = "perception.screen.recover"
        source_id = f"screen-evidence:{evidence_ref}"
        recovery_steps: list[str] = []
        if crop is not None:
            recovery_steps.append("tight_crop")
        if scale > 1:
            recovery_steps.append(f"native_enlarge_x{scale}")

        packet = MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.PERCEPTION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier="soma.screen-recovery",
            ),
            payload={
                "source_id": source_id,
                "native_evidence_ref": evidence_ref,
                "crop": crop.to_dict() if crop is not None else None,
                "scale": scale,
                "max_output_pixels": max_output_pixels,
            },
            authority=self.authority,
            evidence_refs=(evidence_ref,),
            claims=(
                {
                    "kind": "acuity_recovery_request",
                    "source_id": source_id,
                    "epistemic_status": "derived_observation",
                },
            ),
            allowed_destinations=(Gate.DELIBERATION, Gate.MEMORY),
        )

        if not self.authority.allows(permission):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen recovery blocked: missing explicit grant {permission}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-recovery",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    f"missing_grant:{permission}",
                    "sensitive_evidence_not_read",
                    "enhancement_does_not_increase_authority",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_recovery",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                recovery_steps=tuple(recovery_steps),
                recovery_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenRecoveryResult(
                packet=packet,
                receipt=receipt,
                native_evidence_ref=evidence_ref,
                derived_evidence=(),
                observation_evidence_ref=None,
                observation_sha256=None,
                recovery_steps=tuple(recovery_steps),
            )

        if crop is None and scale == 1:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="screen recovery blocked: no_recovery_requested",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-recovery",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=("no_recovery_requested",),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_recovery",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                recovery_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenRecoveryResult(
                packet=packet,
                receipt=receipt,
                native_evidence_ref=evidence_ref,
                derived_evidence=(),
                observation_evidence_ref=None,
                observation_sha256=None,
                recovery_steps=(),
            )

        if scale < 1 or scale > 4 or max_output_pixels <= 0:
            code = "invalid_scale" if scale < 1 or scale > 4 else "invalid_pixel_budget"
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen recovery blocked: {code}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-recovery",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(code,),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_recovery",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                recovery_steps=tuple(recovery_steps),
                recovery_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenRecoveryResult(
                packet=packet,
                receipt=receipt,
                native_evidence_ref=evidence_ref,
                derived_evidence=(),
                observation_evidence_ref=None,
                observation_sha256=None,
                recovery_steps=tuple(recovery_steps),
            )

        if crop is not None:
            try:
                crop.validate_shape()
            except ScreenRecoveryError as exc:
                gate_receipt = self._gate_receipt(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    reason=f"screen recovery blocked: {exc.code}",
                )
                receipt = PerceptionReceipt(
                    **receipt_meta(
                        packet,
                        status=MandalaStatus.BLOCKED,
                        produced_by="soma.screen-recovery",
                        parent_receipt_id=gate_receipt.receipt_id,
                    ),
                    native_evidence_ref=evidence_ref,
                    acuity_status=AcuityStatus.UNAVAILABLE.value,
                    limitations=(exc.code,),
                    source_id=source_id,
                    native_preserved=True,
                    acquisition_method="screen_recovery",
                    acquisition_status="blocked",
                    source_locator=evidence_ref,
                    recovery_steps=tuple(recovery_steps),
                    recovery_backend=provider.name,
                )
                self.ledger.append(receipt)
                return ScreenRecoveryResult(
                    packet=packet,
                    receipt=receipt,
                    native_evidence_ref=evidence_ref,
                    derived_evidence=(),
                    observation_evidence_ref=None,
                    observation_sha256=None,
                    recovery_steps=tuple(recovery_steps),
                )

        try:
            native_bytes = self.evidence.read_bytes(evidence_ref)
        except (ValueError, FileNotFoundError, RuntimeError):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="screen recovery blocked: native_evidence_unavailable",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-recovery",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=("native_evidence_unavailable",),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_recovery",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                recovery_steps=tuple(recovery_steps),
                recovery_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenRecoveryResult(
                packet=packet,
                receipt=receipt,
                native_evidence_ref=evidence_ref,
                derived_evidence=(),
                observation_evidence_ref=None,
                observation_sha256=None,
                recovery_steps=tuple(recovery_steps),
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="native screen evidence admitted for deterministic acuity recovery",
        )

        try:
            frames = provider.recover(
                native_bytes,
                crop=crop,
                scale=scale,
                max_output_pixels=max_output_pixels,
            )
        except ScreenRecoveryError as exc:
            status = (
                MandalaStatus.BLOCKED
                if exc.code
                in {
                    "invalid_crop",
                    "crop_out_of_bounds",
                    "invalid_scale",
                    "invalid_pixel_budget",
                    "output_too_large",
                    "no_recovery_requested",
                }
                else MandalaStatus.QUARANTINED
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=status,
                    produced_by="soma.screen-recovery",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=evidence_ref,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    exc.code,
                    "native_evidence_preserved",
                    "no_derived_observation_promoted",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_recovery",
                acquisition_status=status.value.lower(),
                source_locator=evidence_ref,
                recovery_steps=tuple(recovery_steps),
                recovery_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenRecoveryResult(
                packet=packet,
                receipt=receipt,
                native_evidence_ref=evidence_ref,
                derived_evidence=(),
                observation_evidence_ref=None,
                observation_sha256=None,
                recovery_steps=tuple(recovery_steps),
            )

        derived: list[NativeEvidence] = []
        chain: list[dict[str, Any]] = []
        lineages: list[TransformationLineageReceipt] = []
        parent_ref = evidence_ref
        parent_sha256 = hashlib.sha256(native_bytes).hexdigest()

        if frames.cropped is not None:
            crop_evidence = self.evidence.put_bytes(
                frames.cropped.data,
                media_type=frames.cropped.media_type,
                suffix=frames.cropped.suffix,
            )
            crop_lineage = self.transformations.build(
                transform_id="soma.screen.tight_crop",
                transform_version="v0.1",
                source_refs=(parent_ref,),
                source_sha256s=(parent_sha256,),
                output_ref=crop_evidence.evidence_ref,
                output_sha256=crop_evidence.sha256,
                parameters={
                    "crop": crop.to_dict() if crop is not None else None,
                    "backend": provider.name,
                },
                requested_exactness=ExactnessClass.LOSSY_DERIVED,
                parent_receipts=tuple(lineages[-1:]),
                added_taints=("cropped_context",),
                information_loss_possible=True,
                semantic_inference=False,
                limitations=(
                    "pixels_outside_crop_are_not_present_in_output",
                    "native_source_preserved",
                ),
            )
            derived.append(crop_evidence)
            lineages.append(crop_lineage)
            chain.append(
                {
                    "step": "tight_crop",
                    "input_evidence_ref": parent_ref,
                    "output_evidence_ref": crop_evidence.evidence_ref,
                    "crop": crop.to_dict() if crop is not None else None,
                    "transformation_lineage_sha256": crop_lineage.receipt_sha256,
                }
            )
            parent_ref = crop_evidence.evidence_ref
            parent_sha256 = crop_evidence.sha256

        if frames.enlarged is not None:
            enlarge_evidence = self.evidence.put_bytes(
                frames.enlarged.data,
                media_type=frames.enlarged.media_type,
                suffix=frames.enlarged.suffix,
            )
            enlarge_lineage = self.transformations.build(
                transform_id="soma.screen.native_enlarge",
                transform_version="v0.1",
                source_refs=(parent_ref,),
                source_sha256s=(parent_sha256,),
                output_ref=enlarge_evidence.evidence_ref,
                output_sha256=enlarge_evidence.sha256,
                parameters={
                    "scale": scale,
                    "method": "nearest_neighbor_pixel_replication",
                    "backend": provider.name,
                },
                requested_exactness=ExactnessClass.LOSSY_DERIVED,
                parent_receipts=tuple(lineages[-1:]),
                added_taints=("resampled_pixels",),
                information_loss_possible=True,
                semantic_inference=False,
                limitations=(
                    "resampling_does_not_create_new_native_detail",
                    "reversibility_not_asserted",
                    "native_source_preserved",
                ),
            )
            derived.append(enlarge_evidence)
            lineages.append(enlarge_lineage)
            chain.append(
                {
                    "step": f"native_enlarge_x{scale}",
                    "input_evidence_ref": parent_ref,
                    "output_evidence_ref": enlarge_evidence.evidence_ref,
                    "method": "nearest_neighbor_pixel_replication",
                    "transformation_lineage_sha256": enlarge_lineage.receipt_sha256,
                }
            )
            parent_ref = enlarge_evidence.evidence_ref
            parent_sha256 = enlarge_evidence.sha256

        final = frames.final
        final_evidence = derived[-1]
        final_lineage = lineages[-1]
        receipt = PerceptionReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.ACCEPTED,
                produced_by="soma.screen-recovery",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            native_evidence_ref=evidence_ref,
            acuity_status=AcuityStatus.RECOVERED.value,
            limitations=(
                "derived_observation_not_truth",
                "derived_evidence_never_replaces_native",
                "enhancement_does_not_increase_authority",
                "no_semantic_interpretation",
            ),
            source_id=source_id,
            observation_sha256=final_evidence.sha256,
            native_preserved=True,
            media_type=final.media_type,
            acquisition_method="screen_recovery",
            acquisition_status="accepted",
            source_locator=evidence_ref,
            recovery_steps=tuple(recovery_steps),
            derived_evidence_refs=tuple(item.evidence_ref for item in derived),
            observation_evidence_ref=final_evidence.evidence_ref,
            derivation_chain=tuple(chain),
            recovery_backend=provider.name,
            transformation_lineage_sha256s=tuple(
                item.receipt_sha256 for item in lineages
            ),
            exactness_class=final_lineage.exactness_class.value,
            taint_labels=final_lineage.effective_taints,
        )
        self.ledger.append(receipt)
        return ScreenRecoveryResult(
            packet=packet,
            receipt=receipt,
            native_evidence_ref=evidence_ref,
            derived_evidence=tuple(derived),
            observation_evidence_ref=final_evidence.evidence_ref,
            observation_sha256=final_evidence.sha256,
            recovery_steps=tuple(recovery_steps),
            transformation_lineage=tuple(lineages),
        )


    def perceive_screen_burst(
        self,
        *,
        region: ScreenRegion,
        provider: ScreenCaptureProvider,
        scorer: FrameSharpnessScorer,
        frame_count: int = 3,
        max_pixels: int = 8_294_400,
        max_total_pixels: int = 33_177_600,
    ) -> ScreenBurstResult:
        required = (
            "perception.screen.capture",
            "perception.screen.multishot",
        )
        region_data = region.to_dict()
        source_id = (
            f"screen-burst:{region.x},{region.y},"
            f"{region.width}x{region.height}:{frame_count}"
        )
        packet = self._packet(
            source_id=source_id,
            source_kind=OriginKind.DEVICE,
            native=None,
            payload_extra={
                "capture_region": region_data,
                "capture_backend": provider.name,
                "frame_count": frame_count,
                "max_pixels": max_pixels,
                "max_total_pixels": max_total_pixels,
                "selection_method": scorer.name,
            },
        )

        missing = tuple(permission for permission in required if not self.authority.allows(permission))
        if missing:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="screen burst blocked: missing explicit grant(s)",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-burst",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=tuple(f"missing_grant:{item}" for item in missing)
                + ("visibility_does_not_imply_permission",),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_multishot",
                acquisition_status="blocked",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=provider.name,
                selection_method=scorer.name,
            )
            self.ledger.append(receipt)
            return ScreenBurstResult(
                packet=packet,
                receipt=receipt,
                frame_evidence=(),
                frame_records=(),
                selected_evidence_ref=None,
                observation_sha256=None,
                requested_frames=frame_count,
                valid_frames=0,
            )

        try:
            region.validate(max_pixels=max_pixels)
            if frame_count < 2 or frame_count > 8:
                raise ScreenCaptureError(
                    "invalid_frame_count",
                    "screen burst frame_count must be between 2 and 8",
                )
            if max_total_pixels <= 0:
                raise ScreenCaptureError(
                    "invalid_total_pixel_budget",
                    "max_total_pixels must be positive",
                )
            if region.width * region.height * frame_count > max_total_pixels:
                raise ScreenCaptureError(
                    "burst_too_large",
                    f"burst exceeds max_total_pixels={max_total_pixels}",
                )
        except ScreenCaptureError as exc:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen burst blocked: {exc.code}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-burst",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(exc.code,),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_multishot",
                acquisition_status="blocked",
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=provider.name,
                selection_method=scorer.name,
            )
            self.ledger.append(receipt)
            return ScreenBurstResult(
                packet=packet,
                receipt=receipt,
                frame_evidence=(),
                frame_records=(),
                selected_evidence_ref=None,
                observation_sha256=None,
                requested_frames=frame_count,
                valid_frames=0,
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="explicit screen capture and multishot grants accepted",
        )

        frame_evidence: list[NativeEvidence] = []
        records: list[dict[str, Any]] = []
        valid: list[tuple[int, NativeEvidence, float]] = []

        for index in range(frame_count):
            try:
                frame = provider.capture(region)
            except ScreenCaptureError as exc:
                records.append(
                    {
                        "index": index,
                        "status": "capture_failed",
                        "reason": exc.code,
                        "evidence_ref": None,
                        "score": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                records.append(
                    {
                        "index": index,
                        "status": "capture_failed",
                        "reason": "capture_backend_error",
                        "evidence_ref": None,
                        "score": None,
                    }
                )
                continue

            if not frame.data:
                records.append(
                    {
                        "index": index,
                        "status": "invalid",
                        "reason": "empty_capture",
                        "evidence_ref": None,
                        "score": None,
                    }
                )
                continue

            evidence = self.evidence.put_bytes(
                frame.data,
                media_type=frame.media_type,
                suffix=frame.suffix,
            )
            frame_evidence.append(evidence)

            if frame.media_type != "image/png" or frame.suffix.lower() != ".png":
                records.append(
                    {
                        "index": index,
                        "status": "invalid",
                        "reason": "unsupported_capture_format",
                        "evidence_ref": evidence.evidence_ref,
                        "score": None,
                    }
                )
                continue

            if frame.width != region.width or frame.height != region.height:
                records.append(
                    {
                        "index": index,
                        "status": "invalid",
                        "reason": "capture_dimensions_mismatch",
                        "evidence_ref": evidence.evidence_ref,
                        "score": None,
                    }
                )
                continue

            try:
                score = scorer.score(frame.data)
            except SharpnessScoreError:
                records.append(
                    {
                        "index": index,
                        "status": "invalid",
                        "reason": "sharpness_score_failed",
                        "evidence_ref": evidence.evidence_ref,
                        "score": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - scorer boundary
                records.append(
                    {
                        "index": index,
                        "status": "invalid",
                        "reason": "sharpness_scorer_error",
                        "evidence_ref": evidence.evidence_ref,
                        "score": None,
                    }
                )
                continue

            score_value = float(score)
            records.append(
                {
                    "index": index,
                    "status": "valid",
                    "reason": None,
                    "evidence_ref": evidence.evidence_ref,
                    "score": score_value,
                }
            )
            valid.append((index, evidence, score_value))

        if not valid:
            has_preserved = bool(frame_evidence)
            status = MandalaStatus.QUARANTINED if has_preserved else MandalaStatus.DEGRADED
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=status,
                    produced_by="soma.screen-burst",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    "no_valid_burst_frame",
                    "no_observation_fabricated",
                    "preserved_frames_not_promoted",
                ),
                source_id=source_id,
                native_preserved=has_preserved,
                acquisition_method="screen_multishot",
                acquisition_status=status.value.lower(),
                source_locator=source_id,
                capture_region=region_data,
                capture_backend=provider.name,
                capture_attempts=frame_count,
                burst_frame_refs=tuple(item.evidence_ref for item in frame_evidence),
                burst_frame_records=tuple(records),
                selection_method=scorer.name,
            )
            self.ledger.append(receipt)
            return ScreenBurstResult(
                packet=packet,
                receipt=receipt,
                frame_evidence=tuple(frame_evidence),
                frame_records=tuple(records),
                selected_evidence_ref=None,
                observation_sha256=None,
                requested_frames=frame_count,
                valid_frames=0,
            )

        selected_index, selected, _ = max(valid, key=lambda item: (item[2], -item[0]))
        partial = len(valid) != frame_count
        status = MandalaStatus.DEGRADED if partial else MandalaStatus.ACCEPTED
        limitations = [
            "multishot_selection_is_heuristic",
            "selected_frame_remains_native_evidence",
            "no_frame_fusion",
            "no_semantic_interpretation",
            "selection_does_not_increase_authority",
        ]
        if partial:
            limitations.append("partial_burst")

        receipt = PerceptionReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="soma.screen-burst",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            native_evidence_ref=selected.evidence_ref,
            acuity_status=AcuityStatus.RECOVERED.value,
            limitations=tuple(limitations),
            source_id=source_id,
            native_sha256=selected.sha256,
            observation_sha256=selected.sha256,
            native_preserved=True,
            media_type=selected.media_type,
            acquisition_method="screen_multishot",
            acquisition_status="degraded" if partial else "accepted",
            source_locator=source_id,
            capture_region=region_data,
            capture_backend=provider.name,
            capture_attempts=frame_count,
            recovery_steps=("select_best_native_frame",),
            burst_frame_refs=tuple(item.evidence_ref for item in frame_evidence),
            burst_frame_records=tuple(records),
            selected_evidence_ref=selected.evidence_ref,
            observation_evidence_ref=selected.evidence_ref,
            selection_method=scorer.name,
        )
        self.ledger.append(receipt)

        selected_record = next(item for item in records if item["index"] == selected_index)
        selected_record["selected"] = True

        return ScreenBurstResult(
            packet=packet,
            receipt=receipt,
            frame_evidence=tuple(frame_evidence),
            frame_records=tuple(records),
            selected_evidence_ref=selected.evidence_ref,
            observation_sha256=selected.sha256,
            requested_frames=frame_count,
            valid_frames=len(valid),
        )


    def enhance_screen_evidence(
        self,
        *,
        evidence_ref: str,
        provider: ScreenEnhancementProvider,
        spec: ScreenEnhancementSpec,
    ) -> ScreenEnhancementResult:
        permission = "perception.screen.enhance"
        source_id = f"screen-enhancement:{evidence_ref}"
        parameters = spec.to_dict()

        packet = MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.PERCEPTION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier="soma.screen-enhancement",
            ),
            payload={
                "source_id": source_id,
                "input_evidence_ref": evidence_ref,
                "enhancement": parameters,
            },
            authority=self.authority,
            evidence_refs=(evidence_ref,),
            claims=(
                {
                    "kind": "derived_enhancement_request",
                    "source_id": source_id,
                    "epistemic_status": "derived_observation",
                },
            ),
            allowed_destinations=(Gate.DELIBERATION, Gate.MEMORY),
        )

        if not self.authority.allows(permission):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen enhancement blocked: missing explicit grant {permission}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    f"missing_grant:{permission}",
                    "sensitive_evidence_not_read",
                    "enhancement_does_not_increase_authority",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_enhancement",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=None,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )

        try:
            spec.validate()
        except ScreenEnhancementError as exc:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"screen enhancement blocked: {exc.code}",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(exc.code,),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_enhancement",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=None,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )

        try:
            source_bytes = self.evidence.read_bytes(evidence_ref)
        except (ValueError, FileNotFoundError, RuntimeError):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="screen enhancement blocked: source_evidence_unavailable",
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=("source_evidence_unavailable",),
                source_id=source_id,
                native_preserved=False,
                acquisition_method="screen_enhancement",
                acquisition_status="blocked",
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=None,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="source evidence admitted for bounded deterministic enhancement",
        )

        try:
            frame = provider.enhance(source_bytes, spec=spec)
        except ScreenEnhancementError as exc:
            status = (
                MandalaStatus.BLOCKED
                if exc.code == "input_too_large"
                else MandalaStatus.QUARANTINED
            )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=status,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    exc.code,
                    "source_evidence_preserved",
                    "no_derived_observation_promoted",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_enhancement",
                acquisition_status=status.value.lower(),
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=None,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )
        except Exception:  # noqa: BLE001 - provider boundary
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    "enhancement_backend_error",
                    "source_evidence_preserved",
                    "no_derived_observation_promoted",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_enhancement",
                acquisition_status="quarantined",
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=provider.name,
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=None,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )

        contract_error: str | None = None
        if not frame.data:
            contract_error = "empty_enhancement_output"
        elif frame.media_type != "image/png" or frame.suffix.lower() != ".png":
            contract_error = "unsupported_enhancement_format"
        elif (
            frame.input_width != frame.output_width
            or frame.input_height != frame.output_height
        ):
            contract_error = "enhancement_dimensions_changed"

        if contract_error is not None:
            preserved = None
            if frame.data:
                preserved = self.evidence.put_bytes(
                    frame.data,
                    media_type=frame.media_type,
                    suffix=frame.suffix,
                )
            receipt = PerceptionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.screen-enhancement",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                native_evidence_ref=None,
                acuity_status=AcuityStatus.UNAVAILABLE.value,
                limitations=(
                    contract_error,
                    "source_evidence_preserved",
                    "derived_output_not_promoted",
                ),
                source_id=source_id,
                native_preserved=True,
                acquisition_method="screen_enhancement",
                acquisition_status="quarantined",
                source_locator=evidence_ref,
                input_evidence_ref=evidence_ref,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
                enhancement_backend=frame.backend,
                derived_evidence_refs=(
                    (preserved.evidence_ref,) if preserved is not None else ()
                ),
                derivation_chain=(
                    (
                        {
                            "step": "unsharp_mask_attempt",
                            "input_evidence_ref": evidence_ref,
                            "output_evidence_ref": preserved.evidence_ref,
                            "parameters": parameters,
                            "promoted": False,
                        },
                    )
                    if preserved is not None
                    else ()
                ),
            )
            self.ledger.append(receipt)
            return ScreenEnhancementResult(
                packet=packet,
                receipt=receipt,
                input_evidence_ref=evidence_ref,
                derived_evidence=preserved,
                observation_evidence_ref=None,
                observation_sha256=None,
                enhancement_method=spec.method,
                enhancement_parameters=parameters,
            )

        derived = self.evidence.put_bytes(
            frame.data,
            media_type=frame.media_type,
            suffix=frame.suffix,
        )
        receipt = PerceptionReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.ACCEPTED,
                produced_by="soma.screen-enhancement",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            native_evidence_ref=None,
            acuity_status=AcuityStatus.RECOVERED.value,
            limitations=(
                "derived_observation_not_truth",
                "enhancement_may_amplify_artifacts",
                "enhancement_does_not_recover_lost_information",
                "derived_evidence_never_replaces_source",
                "enhancement_does_not_increase_authority",
                "no_semantic_interpretation",
            ),
            source_id=source_id,
            observation_sha256=derived.sha256,
            native_preserved=True,
            media_type=derived.media_type,
            acquisition_method="screen_enhancement",
            acquisition_status="accepted",
            source_locator=evidence_ref,
            input_evidence_ref=evidence_ref,
            enhancement_method=spec.method,
            enhancement_parameters=parameters,
            enhancement_backend=frame.backend,
            recovery_steps=("deterministic_sharpen",),
            derived_evidence_refs=(derived.evidence_ref,),
            observation_evidence_ref=derived.evidence_ref,
            derivation_chain=(
                {
                    "step": "deterministic_sharpen",
                    "input_evidence_ref": evidence_ref,
                    "output_evidence_ref": derived.evidence_ref,
                    "method": spec.method,
                    "parameters": parameters,
                },
            ),
        )
        self.ledger.append(receipt)
        return ScreenEnhancementResult(
            packet=packet,
            receipt=receipt,
            input_evidence_ref=evidence_ref,
            derived_evidence=derived,
            observation_evidence_ref=derived.evidence_ref,
            observation_sha256=derived.sha256,
            enhancement_method=spec.method,
            enhancement_parameters=parameters,
        )


    def ocr_screen_evidence(
        self,
        *,
        evidence_ref: str,
        provider: OcrProvider,
        spec: OcrSpec,
    ) -> OcrObservationResult:
        permission = "perception.ocr.read"
        source_id = f"ocr:{evidence_ref}"
        spec_data = spec.to_dict()

        packet = MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.PERCEPTION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier="soma.ocr",
            ),
            payload={
                "source_id": source_id,
                "source_evidence_ref": evidence_ref,
                "ocr": spec_data,
            },
            authority=self.authority,
            evidence_refs=(evidence_ref,),
            claims=(
                {
                    "kind": "ocr_interpretation_request",
                    "source_id": source_id,
                    "epistemic_status": "engine_interpretation",
                },
            ),
            allowed_destinations=(Gate.DELIBERATION, Gate.MEMORY),
        )

        if not self.authority.allows(permission):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"OCR blocked: missing explicit grant {permission}",
            )
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=(
                    f"missing_grant:{permission}",
                    "source_evidence_not_read",
                    "ocr_output_is_interpretation",
                ),
                interpretation_status="blocked",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )

        try:
            spec.validate()
        except OcrEngineError as exc:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"OCR blocked: {exc.code}",
            )
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=(exc.code,),
                interpretation_status="blocked",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )

        try:
            source_bytes = self.evidence.read_bytes(evidence_ref)
        except (ValueError, FileNotFoundError, RuntimeError):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="OCR blocked: source_evidence_unavailable",
            )
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=("source_evidence_unavailable",),
                interpretation_status="blocked",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )

        if not source_bytes.startswith(PNG_SIGNATURE):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="OCR blocked: unsupported_ocr_media",
            )
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=(
                    "unsupported_ocr_media",
                    "v0.9_accepts_png_evidence_only",
                ),
                interpretation_status="blocked",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="image evidence admitted for permissioned OCR interpretation",
        )

        try:
            engine_result = provider.read(source_bytes, spec=spec)
        except OcrEngineError as exc:
            status = (
                MandalaStatus.DEGRADED
                if exc.code == "ocr_engine_unavailable"
                else MandalaStatus.QUARANTINED
            )
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=status,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=(
                    exc.code,
                    "source_evidence_preserved",
                    "no_symbolic_interpretation_promoted",
                ),
                interpretation_status=status.value.lower(),
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )
        except Exception:  # noqa: BLE001 - OCR provider boundary
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.QUARANTINED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=provider.name,
                engine_version=None,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                limitations=(
                    "ocr_provider_error",
                    "source_evidence_preserved",
                    "no_symbolic_interpretation_promoted",
                ),
                interpretation_status="quarantined",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text=None,
            )

        valid_confidences = tuple(
            value
            for value in engine_result.confidences
            if 0.0 <= value <= 100.0
        )
        confidence_mean = (
            sum(valid_confidences) / len(valid_confidences)
            if valid_confidences
            else None
        )
        confidence_min = min(valid_confidences) if valid_confidences else None
        confidence_max = max(valid_confidences) if valid_confidences else None
        text = engine_result.text
        stripped = text.strip()

        base_limitations = [
            "ocr_output_is_interpretation",
            "ocr_text_not_truth",
            "confidence_is_engine_metadata_not_probability_of_truth",
            "source_evidence_unchanged",
            "ocr_does_not_increase_authority",
            "no_reality_gate_promotion",
        ]

        if not stripped:
            receipt = OcrReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.DEGRADED,
                    produced_by="soma.ocr",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                source_evidence_ref=evidence_ref,
                output_evidence_ref=None,
                engine=engine_result.engine,
                engine_version=engine_result.engine_version,
                language=spec.language,
                page_segmentation_mode=spec.page_segmentation_mode,
                character_count=0,
                token_count=0,
                confidence_count=len(valid_confidences),
                confidence_mean=confidence_mean,
                confidence_min=confidence_min,
                confidence_max=confidence_max,
                limitations=tuple(base_limitations + ["no_text_detected"]),
                interpretation_status="degraded",
            )
            self.ledger.append(receipt)
            return OcrObservationResult(
                packet=packet,
                receipt=receipt,
                source_evidence_ref=evidence_ref,
                text_evidence=None,
                text="",
            )

        text_evidence = self.evidence.put_text(text)
        limitations = list(base_limitations)
        status = MandalaStatus.ACCEPTED
        if not valid_confidences:
            status = MandalaStatus.DEGRADED
            limitations.append("confidence_unavailable")

        receipt = OcrReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="soma.ocr",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            source_evidence_ref=evidence_ref,
            output_evidence_ref=text_evidence.evidence_ref,
            engine=engine_result.engine,
            engine_version=engine_result.engine_version,
            language=spec.language,
            page_segmentation_mode=spec.page_segmentation_mode,
            text_sha256=text_evidence.sha256,
            character_count=len(text),
            token_count=len(stripped.split()),
            confidence_count=len(valid_confidences),
            confidence_mean=confidence_mean,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            limitations=tuple(limitations),
            interpretation_status=(
                "accepted" if status is MandalaStatus.ACCEPTED else "degraded"
            ),
        )
        self.ledger.append(receipt)
        return OcrObservationResult(
            packet=packet,
            receipt=receipt,
            source_evidence_ref=evidence_ref,
            text_evidence=text_evidence,
            text=text,
        )
