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
from .models import (
    AcuityStatus,
    FileObservationResult,
    NativeEvidence,
    ObservationResult,
    ScreenObservationResult,
    ScreenRecoveryResult,
)
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

        derived = []
        chain: list[dict[str, Any]] = []
        parent_ref = evidence_ref

        if frames.cropped is not None:
            crop_evidence = self.evidence.put_bytes(
                frames.cropped.data,
                media_type=frames.cropped.media_type,
                suffix=frames.cropped.suffix,
            )
            derived.append(crop_evidence)
            chain.append(
                {
                    "step": "tight_crop",
                    "input_evidence_ref": parent_ref,
                    "output_evidence_ref": crop_evidence.evidence_ref,
                    "crop": crop.to_dict() if crop is not None else None,
                }
            )
            parent_ref = crop_evidence.evidence_ref

        if frames.enlarged is not None:
            enlarge_evidence = self.evidence.put_bytes(
                frames.enlarged.data,
                media_type=frames.enlarged.media_type,
                suffix=frames.enlarged.suffix,
            )
            derived.append(enlarge_evidence)
            chain.append(
                {
                    "step": f"native_enlarge_x{scale}",
                    "input_evidence_ref": parent_ref,
                    "output_evidence_ref": enlarge_evidence.evidence_ref,
                    "method": "nearest_neighbor_pixel_replication",
                }
            )
            parent_ref = enlarge_evidence.evidence_ref

        final = frames.final
        final_evidence = derived[-1]
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
        )
