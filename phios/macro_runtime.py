from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class ExecutionMode(StrEnum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    REPLAY = "replay"


class ExecutionState(StrEnum):
    DECLARED = "declared"
    VALIDATING = "validating"
    INVALID = "invalid"
    PLANNED = "planned"
    AWAITING_AUTHORITY = "awaiting_authority"
    DENIED = "denied"
    AUTHORIZED = "authorized"
    READY = "ready"
    EXECUTING = "executing"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    PARTIAL = "partial"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class IdempotencyClass(StrEnum):
    IDEMPOTENT = "idempotent"
    CONDITIONAL = "conditional"
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


class ReplayClass(StrEnum):
    DETERMINISTIC = "deterministic"
    CAPTURE_REQUIRED = "capture_required"
    NON_REPLAYABLE = "non_replayable"
    UNKNOWN = "unknown"


class RollbackClass(StrEnum):
    REVERSIBLE = "reversible"
    COMPENSATING = "compensating"
    NONE = "none"
    UNKNOWN = "unknown"


class SideEffectClass(StrEnum):
    NONE = "none"
    LOCAL_REVERSIBLE = "local_reversible"
    LOCAL_IRREVERSIBLE = "local_irreversible"
    EXTERNAL_REVERSIBLE = "external_reversible"
    EXTERNAL_IRREVERSIBLE = "external_irreversible"
    UNKNOWN = "unknown"


class AuthorityDecisionKind(StrEnum):
    GRANTED = "granted"
    DENIED = "denied"
    PENDING = "pending"


class RuntimeResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    ALREADY_APPLIED = "already_applied"
    DRY_RUN = "dry_run"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CapabilityGrant:
    grant_id: str
    principal_id: str
    capability: str
    scope: str = "*"
    constraints: tuple[str, ...] = ()
    issued_by: str = "operator"
    issued_at: str = ""
    expires_at: str | None = None
    revoked: bool = False


@dataclass(frozen=True)
class AuthorityDecision:
    decision: AuthorityDecisionKind
    principal_id: str
    operation_id: str
    required_capabilities: tuple[str, ...]
    matched_grants: tuple[str, ...]
    missing_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class Operation:
    operation_id: str
    operation_version: str
    adapter_id: str
    action: str
    inputs: dict[str, Any]
    required_capabilities: tuple[str, ...] = ()
    execution_modes_supported: tuple[ExecutionMode, ...] = (
        ExecutionMode.LIVE,
        ExecutionMode.DRY_RUN,
    )
    idempotency_class: IdempotencyClass = IdempotencyClass.UNKNOWN
    replay_class: ReplayClass = ReplayClass.UNKNOWN
    rollback_class: RollbackClass = RollbackClass.UNKNOWN
    side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN
    idempotency_key: str | None = None

    @property
    def operation_hash(self) -> str:
        return _canonical_sha256(
            {
                "operation_id": self.operation_id,
                "operation_version": self.operation_version,
                "adapter_id": self.adapter_id,
                "action": self.action,
                "inputs": self.inputs,
                "required_capabilities": self.required_capabilities,
                "execution_modes_supported": tuple(self.execution_modes_supported),
                "idempotency_class": self.idempotency_class,
                "replay_class": self.replay_class,
                "rollback_class": self.rollback_class,
                "side_effect_class": self.side_effect_class,
                "idempotency_key": self.idempotency_key,
            }
        )

    @property
    def input_hash(self) -> str:
        return _canonical_sha256(self.inputs)


@dataclass(frozen=True)
class AdapterResult:
    output: dict[str, Any]
    committed_side_effect_count: int


class MacroAdapter(Protocol):
    adapter_id: str
    version: str

    def state_hash(self) -> str: ...

    def snapshot(self) -> Any: ...

    def restore(self, snapshot: Any) -> None: ...

    def execute(self, operation: Operation) -> AdapterResult: ...

    def simulate(self, operation: Operation) -> AdapterResult: ...


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    execution_id: str
    state_hash: str
    snapshot: Any


@dataclass(frozen=True)
class RuntimeReceipt:
    receipt_id: str
    execution_id: str
    operation_id: str
    operation_version: str
    principal_id: str
    grant_ids: tuple[str, ...]
    execution_mode: ExecutionMode
    execution_state: ExecutionState
    input_hash: str
    operation_hash: str
    pre_state_hash: str
    post_state_hash: str
    result_hash: str
    committed_side_effect_count: int
    checkpoint_id: str | None
    adapter_id: str
    adapter_version: str
    result_status: RuntimeResultStatus
    started_at: str
    finished_at: str
    parent_receipt_id: str | None = None

    @property
    def receipt_hash(self) -> str:
        return _canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ExecutionResult:
    state: ExecutionState
    status: RuntimeResultStatus
    authority: AuthorityDecision
    receipt: RuntimeReceipt
    output: dict[str, Any]


@dataclass
class MacroRuntime:
    adapters: dict[str, MacroAdapter] = field(default_factory=dict)
    receipts: list[RuntimeReceipt] = field(default_factory=list)
    _committed_idempotency: dict[str, RuntimeReceipt] = field(default_factory=dict)
    _checkpoints: dict[str, Checkpoint] = field(default_factory=dict)

    def register_adapter(self, adapter: MacroAdapter) -> None:
        if not adapter.adapter_id:
            raise ValueError("adapter_id must be non-empty")
        if adapter.adapter_id in self.adapters:
            raise ValueError(f"adapter already registered: {adapter.adapter_id}")
        self.adapters[adapter.adapter_id] = adapter

    def authorize(
        self,
        *,
        principal_id: str,
        operation: Operation,
        grants: tuple[CapabilityGrant, ...],
    ) -> AuthorityDecision:
        active = tuple(
            grant
            for grant in grants
            if grant.principal_id == principal_id and not grant.revoked
        )
        matched = tuple(
            sorted(
                grant.grant_id
                for grant in active
                if grant.capability in operation.required_capabilities
            )
        )
        capabilities = {grant.capability for grant in active}
        missing = tuple(
            capability
            for capability in operation.required_capabilities
            if capability not in capabilities
        )
        decision = (
            AuthorityDecisionKind.GRANTED
            if not missing
            else AuthorityDecisionKind.DENIED
        )
        return AuthorityDecision(
            decision=decision,
            principal_id=principal_id,
            operation_id=operation.operation_id,
            required_capabilities=operation.required_capabilities,
            matched_grants=matched,
            missing_capabilities=missing,
        )

    def execute(
        self,
        *,
        principal_id: str,
        operation: Operation,
        grants: tuple[CapabilityGrant, ...] = (),
        mode: ExecutionMode = ExecutionMode.LIVE,
        parent_receipt_id: str | None = None,
    ) -> ExecutionResult:
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(UTC).isoformat()
        adapter = self._adapter(operation.adapter_id)
        pre_state_hash = adapter.state_hash()

        if mode not in operation.execution_modes_supported:
            raise ValueError(f"execution mode {mode} is not supported")

        authority = self.authorize(
            principal_id=principal_id,
            operation=operation,
            grants=grants,
        )
        if authority.decision is not AuthorityDecisionKind.GRANTED:
            output = {"missing_capabilities": list(authority.missing_capabilities)}
            receipt = self._receipt(
                execution_id=execution_id,
                principal_id=principal_id,
                operation=operation,
                authority=authority,
                mode=mode,
                state=ExecutionState.DENIED,
                pre_state_hash=pre_state_hash,
                post_state_hash=pre_state_hash,
                output=output,
                side_effect_count=0,
                checkpoint_id=None,
                adapter=adapter,
                status=RuntimeResultStatus.DENIED,
                started_at=started_at,
                parent_receipt_id=parent_receipt_id,
            )
            self.receipts.append(receipt)
            return ExecutionResult(
                state=ExecutionState.DENIED,
                status=RuntimeResultStatus.DENIED,
                authority=authority,
                receipt=receipt,
                output=output,
            )

        identity = self._idempotency_identity(operation)
        if mode is ExecutionMode.LIVE and identity is not None:
            prior = self._committed_idempotency.get(identity)
            if prior is not None:
                output = {"prior_receipt_id": prior.receipt_id}
                receipt = self._receipt(
                    execution_id=execution_id,
                    principal_id=principal_id,
                    operation=operation,
                    authority=authority,
                    mode=mode,
                    state=ExecutionState.COMPLETED,
                    pre_state_hash=pre_state_hash,
                    post_state_hash=pre_state_hash,
                    output=output,
                    side_effect_count=0,
                    checkpoint_id=None,
                    adapter=adapter,
                    status=RuntimeResultStatus.ALREADY_APPLIED,
                    started_at=started_at,
                    parent_receipt_id=parent_receipt_id,
                )
                self.receipts.append(receipt)
                return ExecutionResult(
                    state=ExecutionState.COMPLETED,
                    status=RuntimeResultStatus.ALREADY_APPLIED,
                    authority=authority,
                    receipt=receipt,
                    output=output,
                )

        checkpoint = self._create_checkpoint(
            adapter=adapter,
            execution_id=execution_id,
            rollback_class=operation.rollback_class,
        )

        if mode is ExecutionMode.DRY_RUN:
            adapter_result = adapter.simulate(operation)
            if adapter_result.committed_side_effect_count != 0:
                raise RuntimeError("dry-run adapter committed a side effect")
            status = RuntimeResultStatus.DRY_RUN
        elif mode is ExecutionMode.REPLAY:
            if operation.replay_class is not ReplayClass.DETERMINISTIC:
                raise ValueError("operation is not declared deterministic")
            adapter_result = adapter.simulate(operation)
            if adapter_result.committed_side_effect_count != 0:
                raise RuntimeError("replay simulation committed a side effect")
            status = RuntimeResultStatus.SUCCEEDED
        else:
            adapter_result = adapter.execute(operation)
            status = RuntimeResultStatus.SUCCEEDED

        post_state_hash = adapter.state_hash()
        receipt = self._receipt(
            execution_id=execution_id,
            principal_id=principal_id,
            operation=operation,
            authority=authority,
            mode=mode,
            state=ExecutionState.COMPLETED,
            pre_state_hash=pre_state_hash,
            post_state_hash=post_state_hash,
            output=adapter_result.output,
            side_effect_count=adapter_result.committed_side_effect_count,
            checkpoint_id=checkpoint.checkpoint_id if checkpoint else None,
            adapter=adapter,
            status=status,
            started_at=started_at,
            parent_receipt_id=parent_receipt_id,
        )
        self.receipts.append(receipt)
        if mode is ExecutionMode.LIVE and identity is not None:
            self._committed_idempotency[identity] = receipt
        return ExecutionResult(
            state=ExecutionState.COMPLETED,
            status=status,
            authority=authority,
            receipt=receipt,
            output=adapter_result.output,
        )

    def rollback(self, *, receipt_id: str) -> RuntimeReceipt:
        original = self._find_receipt(receipt_id)
        if original.checkpoint_id is None:
            raise ValueError("receipt has no reversible checkpoint")
        checkpoint = self._checkpoints[original.checkpoint_id]
        adapter = self._adapter(original.adapter_id)
        pre_state_hash = adapter.state_hash()
        adapter.restore(checkpoint.snapshot)
        post_state_hash = adapter.state_hash()
        if post_state_hash != checkpoint.state_hash:
            raise RuntimeError("rollback did not restore checkpoint state")
        now = datetime.now(UTC).isoformat()
        receipt = RuntimeReceipt(
            receipt_id=str(uuid.uuid4()),
            execution_id=original.execution_id,
            operation_id=original.operation_id,
            operation_version=original.operation_version,
            principal_id=original.principal_id,
            grant_ids=original.grant_ids,
            execution_mode=original.execution_mode,
            execution_state=ExecutionState.ROLLED_BACK,
            input_hash=original.input_hash,
            operation_hash=original.operation_hash,
            pre_state_hash=pre_state_hash,
            post_state_hash=post_state_hash,
            result_hash=_canonical_sha256({"restored_state_hash": post_state_hash}),
            committed_side_effect_count=0,
            checkpoint_id=original.checkpoint_id,
            adapter_id=original.adapter_id,
            adapter_version=original.adapter_version,
            result_status=RuntimeResultStatus.ROLLED_BACK,
            started_at=now,
            finished_at=now,
            parent_receipt_id=original.receipt_id,
        )
        self.receipts.append(receipt)
        return receipt

    def replay(
        self,
        *,
        principal_id: str,
        operation: Operation,
        original_receipt_id: str,
        grants: tuple[CapabilityGrant, ...] = (),
    ) -> ExecutionResult:
        original = self._find_receipt(original_receipt_id)
        if operation.operation_hash != original.operation_hash:
            raise ValueError("replay operation hash differs from original")
        result = self.execute(
            principal_id=principal_id,
            operation=operation,
            grants=grants,
            mode=ExecutionMode.REPLAY,
            parent_receipt_id=original.receipt_id,
        )
        if result.receipt.result_hash != original.result_hash:
            raise RuntimeError("deterministic replay result hash mismatch")
        return result

    def _adapter(self, adapter_id: str) -> MacroAdapter:
        try:
            return self.adapters[adapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown adapter: {adapter_id}") from exc

    def _create_checkpoint(
        self,
        *,
        adapter: MacroAdapter,
        execution_id: str,
        rollback_class: RollbackClass,
    ) -> Checkpoint | None:
        if rollback_class is not RollbackClass.REVERSIBLE:
            return None
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            execution_id=execution_id,
            state_hash=adapter.state_hash(),
            snapshot=adapter.snapshot(),
        )
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        return checkpoint

    @staticmethod
    def _idempotency_identity(operation: Operation) -> str | None:
        if operation.idempotency_class not in {
            IdempotencyClass.IDEMPOTENT,
            IdempotencyClass.CONDITIONAL,
        }:
            return None
        if not operation.idempotency_key:
            raise ValueError("idempotent operation requires idempotency_key")
        return _canonical_sha256(
            {
                "operation_id": operation.operation_id,
                "operation_version": operation.operation_version,
                "input_hash": operation.input_hash,
                "idempotency_key": operation.idempotency_key,
            }
        )

    def _find_receipt(self, receipt_id: str) -> RuntimeReceipt:
        for receipt in self.receipts:
            if receipt.receipt_id == receipt_id:
                return receipt
        raise KeyError(f"unknown receipt: {receipt_id}")

    @staticmethod
    def _receipt(
        *,
        execution_id: str,
        principal_id: str,
        operation: Operation,
        authority: AuthorityDecision,
        mode: ExecutionMode,
        state: ExecutionState,
        pre_state_hash: str,
        post_state_hash: str,
        output: dict[str, Any],
        side_effect_count: int,
        checkpoint_id: str | None,
        adapter: MacroAdapter,
        status: RuntimeResultStatus,
        started_at: str,
        parent_receipt_id: str | None,
    ) -> RuntimeReceipt:
        return RuntimeReceipt(
            receipt_id=str(uuid.uuid4()),
            execution_id=execution_id,
            operation_id=operation.operation_id,
            operation_version=operation.operation_version,
            principal_id=principal_id,
            grant_ids=authority.matched_grants,
            execution_mode=mode,
            execution_state=state,
            input_hash=operation.input_hash,
            operation_hash=operation.operation_hash,
            pre_state_hash=pre_state_hash,
            post_state_hash=post_state_hash,
            result_hash=_canonical_sha256(output),
            committed_side_effect_count=side_effect_count,
            checkpoint_id=checkpoint_id,
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.version,
            result_status=status,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
            parent_receipt_id=parent_receipt_id,
        )


@dataclass
class InMemoryStateAdapter:
    """Deterministic reference adapter used to prove the v0.1 runtime contract."""

    adapter_id: str = "memory.state"
    version: str = "0.1.0"
    state: dict[str, Any] = field(default_factory=dict)
    committed_effects: int = 0

    def state_hash(self) -> str:
        return _canonical_sha256(self.state)

    def snapshot(self) -> Any:
        return json.loads(json.dumps(self.state, sort_keys=True))

    def restore(self, snapshot: Any) -> None:
        if not isinstance(snapshot, dict):
            raise TypeError("in-memory snapshot must be a dictionary")
        self.state = json.loads(json.dumps(snapshot, sort_keys=True))

    def execute(self, operation: Operation) -> AdapterResult:
        output = self._apply(operation, commit=True)
        return AdapterResult(output=output, committed_side_effect_count=1)

    def simulate(self, operation: Operation) -> AdapterResult:
        output = self._apply(operation, commit=False)
        return AdapterResult(output=output, committed_side_effect_count=0)

    def _apply(self, operation: Operation, *, commit: bool) -> dict[str, Any]:
        if operation.action != "set":
            raise ValueError(f"unsupported action: {operation.action}")
        key = operation.inputs.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("set requires non-empty string key")
        value = operation.inputs.get("value")
        predicted = dict(self.state)
        predicted[key] = value
        if commit:
            self.state = predicted
            self.committed_effects += 1
        return {
            "key": key,
            "value": value,
            "predicted_state_hash": _canonical_sha256(predicted),
        }
