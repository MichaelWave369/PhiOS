from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .collaborator import PhiVesselAdapter
from .executor import ExecutorRegistry, text_artifact_handler
from .gate import PermissionGate
from .ledger import RealityLedger
from .models import Capability, ExecutionReceipt
from .registry import CapabilityRegistry


class PhiOSSpine:
    """First vertical slice of PhiOS authority-aware execution."""

    def __init__(
        self,
        state_root: Path | None = None,
        allowed_permissions: Iterable[str] = (),
    ) -> None:
        self.state_root = (state_root or Path.home() / ".phios" / "spine-v0.1").expanduser()
        self.registry = CapabilityRegistry()
        self.gate = PermissionGate(allowed_permissions)
        self.executors = ExecutorRegistry()
        self.vessel = PhiVesselAdapter()
        self.ledger = RealityLedger(self.state_root / "ledger" / "receipts.jsonl")
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

    def run(self, capability_id: str, payload: dict[str, Any]) -> ExecutionReceipt:
        plan = self.vessel.plan(capability_id=capability_id, payload=payload)
        capability = self.registry.get(plan.capability_id)
        decision = self.gate.evaluate(capability)
        receipt = ExecutionReceipt(
            schema_version="phios.execution_receipt.v0.1",
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            capability_id=capability.id,
            planner=plan.planner,
            input_sha256=self._hash_payload(plan.payload),
            permissions_requested=list(decision.requested),
            permission_status="allowed" if decision.allowed else "denied",
            execution_status="not_executed",
        )
        if not decision.allowed:
            receipt.error = decision.reason
            self.ledger.append(receipt)
            return receipt

        try:
            artifact = self.executors.execute(capability.id, plan.payload)
            receipt.execution_status = "succeeded"
            receipt.artifact_path = str(artifact.path)
            receipt.artifact_sha256 = artifact.sha256
        except Exception as exc:
            receipt.execution_status = "failed"
            receipt.error = f"{type(exc).__name__}: {exc}"

        self.ledger.append(receipt)
        return receipt
