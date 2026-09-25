from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from phios.mandala import (
    AbortReceipt,
    ActionReceipt,
    DeliberationEvidenceAssessor,
    DeliberationEvidenceResult,
    EffectBoundaryReceipt,
    EscalationRequest,
    EvidencePathDeclaration,
    GovernanceEscalationResult,
    GovernanceEscalationService,
    Gate,
    GateReceipt,
    MandalaPacket,
    MandalaReceiptLedger,
    MandalaStatus,
    IndependenceAssertion,
    OriginKind,
    OriginRef,
    PhiCoreState,
)
from phios.mandala.receipts import receipt_meta
from phios.reality import (
    InterfaceStateProvider,
    LocalHttpStateProvider,
    RealityClaim,
    RealityVerificationResult,
    RealityVerificationService,
    TcpListenerStateProvider,
)
from phios.soma import (
    FileObservationResult,
    ObservationResult,
    OcrObservationResult,
    OcrProvider,
    OcrSpec,
    PillowEdgeSharpnessScorer,
    PillowScreenCaptureProvider,
    PillowUnsharpMaskProvider,
    PillowScreenRecoveryProvider,
    FrameSharpnessScorer,
    ScreenBurstResult,
    ScreenCaptureProvider,
    ScreenEnhancementProvider,
    ScreenEnhancementResult,
    ScreenEnhancementSpec,
    ScreenObservationResult,
    ScreenRecoveryProvider,
    ScreenRecoveryResult,
    ScreenCrop,
    ScreenRegion,
    SomaPerceptionService,
    TesseractOcrProvider,
)

from .api_keys import ApiKeyBoundary
from .collaborator import PhiVesselAdapter
from .effects import EffectBoundaryPolicy
from .executor import ExecutorRegistry, OutcomeUnknownError, text_artifact_handler
from .gate import PermissionGate
from .ledger import RealityLedger
from .models import Capability, ExecutionProvenance, ExecutionReceipt
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
        self.api_keys = ApiKeyBoundary()
        self.effect_policy = EffectBoundaryPolicy()
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
        self.reality = RealityVerificationService(
            evidence=self.soma.evidence,
            ledger=self.mandala_ledger,
            task_id=self.core.task_id,
            authority=self.core.authority,
        )
        self.deliberation_evidence = DeliberationEvidenceAssessor(
            self.mandala_ledger
        )
        self.governance_escalation = GovernanceEscalationService(
            self.mandala_ledger
        )
        self._register_builtins()

    def _register_builtins(self) -> None:
        capability = Capability(
            id="commons.text_artifact",
            name="Text Artifact",
            description="Write user-supplied text into the PhiOS artifact store.",
            permissions=("artifact.write",),
            effects=("filesystem.change",),
            risk="low",
        )
        self.registry.register(capability)
        self.executors.register(
            capability.id,
            text_artifact_handler(self.state_root / "artifacts"),
            effects=("filesystem.change",),
        )

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
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

    def perceive_screen_burst(
        self,
        *,
        region: ScreenRegion,
        provider: ScreenCaptureProvider | None = None,
        scorer: FrameSharpnessScorer | None = None,
        frame_count: int = 3,
        max_pixels: int = 8_294_400,
        max_total_pixels: int = 33_177_600,
    ) -> ScreenBurstResult:
        capture_provider = provider or PillowScreenCaptureProvider()
        sharpness_scorer = scorer or PillowEdgeSharpnessScorer()
        return self.soma.perceive_screen_burst(
            region=region,
            provider=capture_provider,
            scorer=sharpness_scorer,
            frame_count=frame_count,
            max_pixels=max_pixels,
            max_total_pixels=max_total_pixels,
        )

    def ocr_screen_evidence(
        self,
        *,
        evidence_ref: str,
        spec: OcrSpec | None = None,
        provider: OcrProvider | None = None,
    ) -> OcrObservationResult:
        ocr_provider = provider or TesseractOcrProvider()
        ocr_spec = spec or OcrSpec()
        return self.soma.ocr_screen_evidence(
            evidence_ref=evidence_ref,
            provider=ocr_provider,
            spec=ocr_spec,
        )

    def verify_reality(
        self,
        *,
        claims: tuple[RealityClaim, ...],
        max_evidence_bytes: int = 1_048_576,
        interface_provider: InterfaceStateProvider | None = None,
        tcp_listener_provider: TcpListenerStateProvider | None = None,
        local_http_provider: LocalHttpStateProvider | None = None,
    ) -> RealityVerificationResult:
        return self.reality.verify(
            claims=claims,
            max_evidence_bytes=max_evidence_bytes,
            interface_provider=interface_provider,
            tcp_listener_provider=tcp_listener_provider,
            local_http_provider=local_http_provider,
        )

    def assess_deliberation_evidence(
        self,
        *,
        claim_id: str,
        paths: tuple[EvidencePathDeclaration, ...],
        assertions: tuple[IndependenceAssertion, ...] = (),
    ) -> DeliberationEvidenceResult:
        evidence_refs = tuple(
            sorted(
                {
                    ref
                    for path in paths
                    for ref in path.evidence_refs
                }
            )
        )
        packet = MandalaPacket.create(
            task_id=self.core.task_id,
            gate=Gate.DELIBERATION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier="phivessel.deliberation",
            ),
            payload={
                "claim_id": claim_id,
                "path_ids": [path.path_id for path in paths],
            },
            authority=self.core.authority,
            evidence_refs=evidence_refs,
            claims=(
                {
                    "kind": "evidence_independence_assessment",
                    "claim_id": claim_id,
                },
            ),
            allowed_destinations=(Gate.MEMORY,),
        )
        return self.deliberation_evidence.assess(
            packet=packet,
            claim_id=claim_id,
            paths=paths,
            assertions=assertions,
        )

    def escalate_reality_finding(
        self,
        *,
        verification: RealityVerificationResult,
        disposition: str,
        trigger_claim_ids: tuple[str, ...],
        reason: str,
        target_ref: str,
        candidate_capability_id: str | None = None,
        candidate_payload: dict[str, Any] | None = None,
    ) -> GovernanceEscalationResult:
        if verification.receipt.task_id != self.core.task_id:
            raise ValueError(
                "reality escalation source must belong to the active Spine task"
            )
        if verification.receipt.packet_id != verification.packet.packet_id:
            raise ValueError(
                "reality escalation packet/receipt identity mismatch"
            )

        normalized_disposition = disposition.strip().upper()
        capability_id: str | None = None
        capability_version: str | None = None
        capability_risk: str | None = None
        capability_contract_sha256: str | None = None
        payload_sha256: str | None = None
        permissions: tuple[str, ...] = ()
        effects: tuple[str, ...] = ()

        if normalized_disposition == "REMEDIATE":
            if candidate_capability_id is None or candidate_payload is None:
                raise ValueError(
                    "REMEDIATE escalation requires capability and payload"
                )
            capability = self.registry.get(candidate_capability_id)
            capability_id = capability.id
            capability_version = capability.version
            capability_risk = str(capability.risk)
            capability_contract_sha256 = self._hash_payload(
                capability.to_dict()
            )
            payload_sha256 = self._hash_payload(candidate_payload)
            permissions = tuple(capability.permissions)
            effects = tuple(capability.effects)
        elif candidate_capability_id is not None or candidate_payload is not None:
            raise ValueError(
                "non-remediation escalation cannot carry an action candidate"
            )

        request = EscalationRequest.create(
            disposition=normalized_disposition,
            reason=reason,
            target_ref=target_ref,
            trigger_claim_ids=trigger_claim_ids,
            candidate_capability_id=capability_id,
            candidate_capability_version=capability_version,
            candidate_capability_risk=capability_risk,
            candidate_capability_contract_sha256=capability_contract_sha256,
            candidate_payload_sha256=payload_sha256,
            requested_permissions=permissions,
            requested_effects=effects,
        )
        return self.governance_escalation.assess(
            source_receipt=verification.receipt,
            request=request,
        )

    def enhance_screen_evidence(
        self,
        *,
        evidence_ref: str,
        spec: ScreenEnhancementSpec | None = None,
        provider: ScreenEnhancementProvider | None = None,
    ) -> ScreenEnhancementResult:
        enhancement_provider = provider or PillowUnsharpMaskProvider()
        enhancement_spec = spec or ScreenEnhancementSpec()
        return self.soma.enhance_screen_evidence(
            evidence_ref=evidence_ref,
            provider=enhancement_provider,
            spec=enhancement_spec,
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

    def _effect_receipt(
        self,
        packet: MandalaPacket,
        capability: Capability,
    ) -> EffectBoundaryReceipt:
        try:
            executor_effects = self.executors.effects(capability.id)
        except KeyError:
            executor_effects = ()
        decision = self.effect_policy.evaluate(
            capability,
            executor_effects=executor_effects,
        )
        body = EffectBoundaryReceipt(
            **receipt_meta(
                packet,
                status=(
                    MandalaStatus.ACCEPTED
                    if decision.allowed
                    else MandalaStatus.BLOCKED
                ),
                produced_by="phios.effect_boundary",
            ),
            capability_id=decision.capability_id,
            capability_version=decision.capability_version,
            capability_risk=decision.capability_risk,
            capability_effects=decision.capability_effects,
            executor_effects=decision.executor_effects,
            active_effects=decision.active_effects,
            effect_contract_match=decision.effect_contract_match,
            classification_complete=decision.classification_complete,
            semantic_read_label_conflict=decision.semantic_read_label_conflict,
            effect_policy_sha256=decision.policy_sha256,
            reason=decision.reason,
        )
        return replace(
            body,
            receipt_sha256=self._hash_payload(body.to_dict()),
        )

    def _gate_receipt(
        self,
        packet: MandalaPacket,
        *,
        allowed: bool,
        reason: str,
        parent_receipt_id: str | None = None,
    ) -> GateReceipt:
        return GateReceipt(
            **receipt_meta(
                packet,
                status=MandalaStatus.ACCEPTED if allowed else MandalaStatus.BLOCKED,
                produced_by="phios.action_gate",
                parent_receipt_id=parent_receipt_id,
            ),
            gate=Gate.ACTION,
            reason=reason,
            provenance_refs=packet.evidence_refs,
            authority=packet.authority.to_dict(),
        )

    def run(
        self,
        capability_id: str,
        payload: dict[str, Any],
        *,
        governed_provenance: ExecutionProvenance | None = None,
    ) -> ExecutionReceipt:
        plan = self.vessel.plan(capability_id=capability_id, payload=payload)
        capability = self.registry.get(plan.capability_id)
        packet = self._action_packet(plan, capability)

        effect_receipt = self._effect_receipt(packet, capability)
        self.mandala_ledger.append(effect_receipt)
        if effect_receipt.status is MandalaStatus.BLOCKED:
            gate_receipt = self._gate_receipt(
                packet,
                allowed=False,
                reason=f"Effect boundary blocked: {effect_receipt.reason}",
                parent_receipt_id=effect_receipt.receipt_id,
            )
            self.mandala_ledger.append(gate_receipt)
            receipt = ExecutionReceipt(
                schema_version="phios.execution_receipt.v0.1",
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                capability_id=capability.id,
                planner=plan.planner,
                input_sha256=self._hash_payload(plan.payload),
                permissions_requested=list(capability.permissions),
                permission_status="denied",
                execution_status="not_executed",
                packet_id=packet.packet_id,
                gate_receipt_id=gate_receipt.receipt_id,
                governed_provenance=governed_provenance,
                error=f"effect_boundary:{effect_receipt.reason}",
            )
            action_receipt = ActionReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="phios.action_gate",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                approved_grant=(),
                side_effect={
                    "capability_id": capability.id,
                    "effect_boundary_receipt_id": effect_receipt.receipt_id,
                },
                outcome="not_executed",
                external_identifiers={},
            )
            self.mandala_ledger.append(action_receipt)
            receipt.action_receipt_id = action_receipt.receipt_id
            receipt.mandala_status = action_receipt.status.value
            self.ledger.append(receipt)
            return receipt

        decision = self.gate.evaluate(capability)
        gate_receipt = self._gate_receipt(
            packet,
            allowed=decision.allowed,
            reason=decision.reason,
            parent_receipt_id=effect_receipt.receipt_id,
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
            governed_provenance=governed_provenance,
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

        receipt.executor_entered = True
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
        except OutcomeUnknownError as exc:
            receipt.execution_status = "outcome_unknown"
            receipt.reconciliation_status = "required"
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
                outcome="outcome_unknown",
                external_identifiers=exc.external_identifiers,
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
