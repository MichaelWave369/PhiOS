from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from phios.mandala import (
    AbortReceipt,
    ActionReceipt,
    Gate,
    GateReceipt,
    MandalaPacket,
    MandalaReceiptLedger,
    MandalaStatus,
    OriginKind,
    OriginRef,
    PhiCoreState,
)
from phios.mandala.receipts import receipt_meta
from phios.soma import (
    FileObservationResult,
    ObservationResult,
    PillowScreenCaptureProvider,
    PillowScreenRecoveryProvider,
    ScreenCaptureProvider,
    ScreenObservationResult,
    ScreenRecoveryProvider,
    ScreenRecoveryResult,
    ScreenCrop,
    ScreenRegion,
    SomaPerceptionService,
)

from .collaborator import PhiVesselAdapter
from .executor import ExecutorRegistry, text_artifact_handler
from .gate import PermissionGate
from .ledger import RealityLedger
from .models import Capability, ExecutionReceipt
from .registry import CapabilityRegistry


class PhiOSSpine:
    """Authority-aware execution spine with Mandala gates and SOMA perception."""

    def __init__(
        self,
        state_root: Path | None = None,
        allowed_permissions: Iterable[str] = (),
        task_id: str | None = None,
    ) -> None:
        self.state_root = (state_root or Path.home() / ".phios" / "spine-v0.1").expanduser()
        allowed = tuple(dict.fromkeys(allowed_permissions))
        self.registry = CapabilityRegistry()
        self.gate = PermissionGate(allowed)
        self.executors = ExecutorRegistry()
        self.vessel = PhiVesselAdapter()
        self.ledger = RealityLedger(self.state_root / "ledger" / "receipts.jsonl")
        self.mandala_ledger = MandalaReceiptLedger(
            self.state_root / "ledger" / "mandala-receipts.jsonl"
        )
        self.core = PhiCoreState.initialize(
            task_id=task_id,
            authority_ceiling=allowed,
            explicit_grants=allowed,
            ledger_pointer=str(self.mandala_ledger.path),
        ).activate()
        self.soma = SomaPerceptionService(
            state_root=self.state_root,
            ledger=self.mandala_ledger,
            task_id=self.core.task_id,
            authority=self.core.authority,
        )
        self._register_builtins()

    def _register_builtins(self) -> None:
        capability = Capability(
            id="commons.text_artifact",
            name="Text Artifact",
            description="Write user-supplied text into the PhiOS artifact store.",
            permissions=("artifact.write",),
            risk="low",
        )
        self.registry.register(capability)
        self.executors.register(
            capability.id,
            text_artifact_handler(self.state_root / "artifacts"),
        )

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def perceive_text(
        self,
        *,
        source_id: str,
        text: str,
        transforms: tuple[str, ...] = (),
        source_kind: OriginKind = OriginKind.HUMAN,
    ) -> ObservationResult:
        return self.soma.perceive_text(
            source_id=source_id,
            text=text,
            transforms=transforms,
            source_kind=source_kind,
        )

    def perceive_file(
        self,
        *,
        source_root: Path,
        relative_path: str,
        transforms: tuple[str, ...] = (),
        max_bytes: int = 1_048_576,
    ) -> FileObservationResult:
        return self.soma.perceive_file(
            source_root=source_root,
            relative_path=relative_path,
            transforms=transforms,
            max_bytes=max_bytes,
        )

    def perceive_screen(
        self,
        *,
        region: ScreenRegion,
        provider: ScreenCaptureProvider | None = None,
        max_pixels: int = 8_294_400,
        reacquire_attempts: int = 1,
    ) -> ScreenObservationResult:
        capture_provider = provider or PillowScreenCaptureProvider()
        return self.soma.perceive_screen(
            region=region,
            provider=capture_provider,
            max_pixels=max_pixels,
            reacquire_attempts=reacquire_attempts,
        )

    def recover_screen_evidence(
        self,
        *,
        evidence_ref: str,
        crop: ScreenCrop | None = None,
        scale: int = 1,
        max_output_pixels: int = 16_777_216,
        provider: ScreenRecoveryProvider | None = None,
    ) -> ScreenRecoveryResult:
        recovery_provider = provider or PillowScreenRecoveryProvider()
        return self.soma.recover_screen_evidence(
            evidence_ref=evidence_ref,
            provider=recovery_provider,
            crop=crop,
            scale=scale,
            max_output_pixels=max_output_pixels,
        )

    def _action_packet(self, plan: Any, capability: Capability) -> MandalaPacket:
        return MandalaPacket.create(
            task_id=self.core.task_id,
            gate=Gate.ACTION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier=plan.planner,
            ),
            payload=plan.payload,
            authority=self.core.authority,
            claims=(
                {
                    "kind": "action_request",
                    "capability_id": capability.id,
                },
            ),
            allowed_destinations=(Gate.MEMORY,),
        )

    def _gate_receipt(
        self,
        packet: MandalaPacket,
        *,
        allowed: bool,
        reason: str,
    ) -> GateReceipt:
        return GateReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.ACCEPTED if allowed else MandalaStatus.BLOCKED,
                produced_by="phios.action_gate",
            ),
            gate=Gate.ACTION,
            reason=reason,
            provenance_refs=packet.evidence_refs,
            authority=packet.authority.to_dict(),
        )

    def run(self, capability_id: str, payload: dict[str, Any]) -> ExecutionReceipt:
        plan = self.vessel.plan(capability_id=capability_id, payload=payload)
        capability = self.registry.get(plan.capability_id)
        packet = self._action_packet(plan, capability)
        decision = self.gate.evaluate(capability)

        gate_receipt = self._gate_receipt(
            packet,
            allowed=decision.allowed,
            reason=decision.reason,
        )
        self.mandala_ledger.append(gate_receipt)

        receipt = ExecutionReceipt(
            schema_version="phios.execution_receipt.v0.1",
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            capability_id=capability.id,
            planner=plan.planner,
            input_sha256=self._hash_payload(plan.payload),
            permissions_requested=list(decision.requested),
            permission_status="allowed" if decision.allowed else "denied",
            execution_status="not_executed",
            packet_id=packet.packet_id,
            gate_receipt_id=gate_receipt.receipt_id,
        )

        if not decision.allowed:
            action_receipt = ActionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="phios.action_gate",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                approved_grant=decision.granted,
                side_effect={"capability_id": capability.id},
                outcome="not_executed",
                external_identifiers={},
            )
            self.mandala_ledger.append(action_receipt)
            receipt.action_receipt_id = action_receipt.receipt_id
            receipt.mandala_status = action_receipt.status.value
            receipt.error = decision.reason
            self.ledger.append(receipt)
            return receipt

        try:
            artifact = self.executors.execute(capability.id, plan.payload)
            receipt.execution_status = "succeeded"
            receipt.artifact_path = str(artifact.path)
            receipt.artifact_sha256 = artifact.sha256
            action_receipt = ActionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.ACCEPTED,
                    produced_by="phios.action_gate",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                approved_grant=decision.granted,
                side_effect={"capability_id": capability.id},
                outcome="succeeded",
                external_identifiers={
                    "artifact_path": str(artifact.path),
                    "artifact_sha256": artifact.sha256,
                },
            )
            self.mandala_ledger.append(action_receipt)
        except Exception as exc:  # noqa: BLE001 - executor boundary receipts arbitrary failures
            receipt.execution_status = "failed"
            receipt.error = f"{type(exc).__name__}: {exc}"
            action_receipt = ActionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.ABORTED,
                    produced_by="phios.action_gate",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                approved_grant=decision.granted,
                side_effect={"capability_id": capability.id},
                outcome="failed",
                external_identifiers={},
            )
            self.mandala_ledger.append(action_receipt)
            abort_receipt = AbortReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.ABORTED,
                    produced_by="phios.runtime",
                    parent_receipt_id=action_receipt.receipt_id,
                ),
                terminal_reason=receipt.error,
                eligible_artifacts=(),
                quarantined_artifacts=(),
            )
            self.mandala_ledger.append(abort_receipt)

        receipt.action_receipt_id = action_receipt.receipt_id
        receipt.mandala_status = action_receipt.status.value
        self.ledger.append(receipt)
        return receipt
