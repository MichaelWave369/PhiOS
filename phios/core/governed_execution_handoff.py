"""Governed execution handoff for PhiOS core reasoning v0.8.

This layer revalidates one exact adopted-plan action binding at execution time,
blocks consumed binding replay, and delegates permission evaluation and side
effects to the existing PhiOS Spine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from phios.action_lease import ActionLease, evaluate_action_lease
from phios.core.governed_action_binding import (
    ActionBindingContractError,
    GovernedActionBinder,
    PlanActionBinding,
)
from phios.core.governed_plan_adoption import (
    GovernedPlanAdoptionGate,
    PlanAdoptionContractError,
    PlanState,
)
from phios.spine.effects import EffectBoundaryContractError, normalize_effects
from phios.spine.models import ExecutionProvenance, ExecutionReceipt
from phios.spine.runtime import PhiOSSpine


class ExecutionHandoffContractError(ValueError):
    """Raised when governed execution handoff inputs are malformed."""


@dataclass(frozen=True, slots=True)
class ExecutionHandoffReceipt:
    """Runtime receipt for HELD / DENIED / SUCCEEDED / FAILED handoff outcomes."""

    schema: str
    status: str
    reason: str
    plan_id: str
    plan_state_sha256: str
    plan_revision: int
    transition_index: int
    source_state_id: str
    target_state_id: str
    capability_id: str
    payload_sha256: str
    action_binding_sha256: str
    binding_consumed: bool
    replay_blocked: bool
    spine_receipt_id: str | None
    spine_permission_status: str | None
    spine_execution_status: str | None
    gate_receipt_id: str | None
    action_receipt_id: str | None
    mandala_status: str | None
    artifact_path: str | None
    artifact_sha256: str | None
    action_lease_sha256: str | None
    lease_consumed: bool
    lease_evaluation_reason: str | None
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "plan_id": self.plan_id,
            "plan_state_sha256": self.plan_state_sha256,
            "plan_revision": self.plan_revision,
            "transition_index": self.transition_index,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
            "capability_id": self.capability_id,
            "payload_sha256": self.payload_sha256,
            "action_binding_sha256": self.action_binding_sha256,
            "binding_consumed": self.binding_consumed,
            "replay_blocked": self.replay_blocked,
            "spine_receipt_id": self.spine_receipt_id,
            "spine_permission_status": self.spine_permission_status,
            "spine_execution_status": self.spine_execution_status,
            "gate_receipt_id": self.gate_receipt_id,
            "action_receipt_id": self.action_receipt_id,
            "mandala_status": self.mandala_status,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "action_lease_sha256": self.action_lease_sha256,
            "lease_consumed": self.lease_consumed,
            "lease_evaluation_reason": self.lease_evaluation_reason,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedExecutionHandoff:
    """TOCTOU-safe handoff from v0.7 binding into the existing Spine."""

    def __init__(self) -> None:
        self._plan_gate = GovernedPlanAdoptionGate()
        self._binder = GovernedActionBinder()

    def execute_with_lease(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        spine: PhiOSSpine,
        lease: ActionLease,
        checked_at: str,
        current_authority_epoch_sha256: str,
        trusted_issuer_ids: tuple[str, ...],
        accepted_authorization_receipt_sha256s: tuple[str, ...],
    ) -> ExecutionHandoffReceipt:
        """Execute only after a bounded ActionLease passes runtime validation."""

        self._validate_inputs(plan, binding)

        if lease.issuer_id not in set(trusted_issuer_ids):
            return self._held_with_lease(
                plan=plan,
                binding=binding,
                lease=lease,
                reason="action_lease_issuer_untrusted",
                evaluation_reason="issuer_untrusted",
            )
        if lease.authorization_receipt_sha256 not in set(
            accepted_authorization_receipt_sha256s
        ):
            return self._held_with_lease(
                plan=plan,
                binding=binding,
                lease=lease,
                reason="action_lease_authorization_receipt_unaccepted",
                evaluation_reason="authorization_receipt_unaccepted",
            )

        scope_reason = self._lease_scope(binding, lease)
        if scope_reason is not None:
            return self._held_with_lease(
                plan=plan,
                binding=binding,
                lease=lease,
                reason=scope_reason,
                evaluation_reason="scope_mismatch",
            )

        try:
            consumed = spine.ledger.has_consumed_action_lease(
                lease.action_lease_sha256
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ExecutionHandoffContractError(
                "action lease consumption state could not be verified safely"
            ) from exc

        evaluation = evaluate_action_lease(
            lease=lease,
            checked_at=checked_at,
            current_authority_epoch_sha256=current_authority_epoch_sha256,
            uses_consumed=1 if consumed else 0,
        )
        if not evaluation.usable:
            return self._held_with_lease(
                plan=plan,
                binding=binding,
                lease=lease,
                reason=f"action_lease_{evaluation.reason}",
                evaluation_reason=evaluation.reason,
                replay_blocked=(evaluation.reason == "lease_consumed"),
            )

        try:
            lease_claimed = spine.ledger.claim_action_lease(
                lease.action_lease_sha256
            )
        except (OSError, ValueError) as exc:
            raise ExecutionHandoffContractError(
                "action lease could not be claimed safely"
            ) from exc
        if not lease_claimed:
            return self._held_with_lease(
                plan=plan,
                binding=binding,
                lease=lease,
                reason="action_lease_claim_unavailable",
                evaluation_reason="claim_unavailable",
                replay_blocked=True,
            )

        try:
            receipt = self.execute(
                plan=plan,
                binding=binding,
                payload=payload,
                spine=spine,
            )
        except Exception:
            try:
                attempted = spine.ledger.has_consumed_binding(
                    binding.binding_sha256
                )
                if attempted:
                    spine.ledger.mark_action_lease_consumed(
                        lease_sha256=lease.action_lease_sha256,
                        binding_sha256=binding.binding_sha256,
                        spine_receipt_id=None,
                        outcome="attempted_outcome_unknown",
                    )
                else:
                    spine.ledger.release_action_lease_claim(
                        lease.action_lease_sha256
                    )
            except (OSError, json.JSONDecodeError, ValueError):
                pass
            raise

        if receipt.binding_consumed:
            try:
                spine.ledger.mark_action_lease_consumed(
                    lease_sha256=lease.action_lease_sha256,
                    binding_sha256=binding.binding_sha256,
                    spine_receipt_id=receipt.spine_receipt_id,
                    outcome=receipt.status,
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ExecutionHandoffContractError(
                    "action lease consumption could not be recorded safely"
                ) from exc
            return self._attach_lease(
                receipt,
                lease=lease,
                lease_consumed=True,
                evaluation_reason=evaluation.reason,
            )

        try:
            spine.ledger.release_action_lease_claim(
                lease.action_lease_sha256
            )
        except (OSError, ValueError) as exc:
            raise ExecutionHandoffContractError(
                "unused action lease claim could not be released safely"
            ) from exc
        return self._attach_lease(
            receipt,
            lease=lease,
            lease_consumed=False,
            evaluation_reason=evaluation.reason,
        )

    def execute(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        spine: PhiOSSpine,
    ) -> ExecutionHandoffReceipt:
        self._validate_inputs(plan, binding)

        scope_reason = self._current_plan_scope(plan, binding)
        if scope_reason is not None:
            return self._held(
                plan=plan,
                binding=binding,
                reason=scope_reason,
            )

        try:
            payload_sha256 = self._binder.payload_sha256(payload)
        except ActionBindingContractError as exc:
            raise ExecutionHandoffContractError(str(exc)) from exc
        if payload_sha256 != binding.payload_sha256:
            return self._held(
                plan=plan,
                binding=binding,
                reason="payload_digest_mismatch",
            )

        try:
            capability = spine.registry.get(binding.capability_id)
        except KeyError:
            return self._held(
                plan=plan,
                binding=binding,
                reason="capability_not_registered",
            )

        current_permissions = tuple(capability.permissions)
        try:
            current_effects = normalize_effects(
                capability.effects,
                label="runtime capability effects",
            )
        except EffectBoundaryContractError:
            return self._held(
                plan=plan,
                binding=binding,
                reason="capability_effect_contract_invalid",
            )
        if (
            capability.version != binding.capability_version
            or str(capability.risk) != binding.capability_risk
            or current_permissions != binding.permissions_requested
            or current_effects != binding.effects_declared
        ):
            return self._held(
                plan=plan,
                binding=binding,
                reason="capability_contract_drift",
            )

        try:
            executor_effects = spine.executors.effects(capability.id)
        except KeyError:
            return self._held(
                plan=plan,
                binding=binding,
                reason="executor_effect_contract_missing",
            )
        effect_decision = spine.effect_policy.evaluate(
            capability,
            executor_effects=executor_effects,
        )
        if not effect_decision.allowed:
            return self._held(
                plan=plan,
                binding=binding,
                reason=f"effect_boundary_{effect_decision.reason}",
            )

        try:
            consumed = spine.ledger.has_consumed_binding(binding.binding_sha256)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ExecutionHandoffContractError(
                "execution ledger could not be verified safely"
            ) from exc
        if consumed:
            return self._held(
                plan=plan,
                binding=binding,
                reason="binding_already_consumed",
                replay_blocked=True,
            )

        try:
            claimed = spine.ledger.claim_binding(binding.binding_sha256)
        except (OSError, ValueError) as exc:
            raise ExecutionHandoffContractError(
                "execution binding could not be claimed safely"
            ) from exc
        if not claimed:
            return self._held(
                plan=plan,
                binding=binding,
                reason="binding_execution_claim_unavailable",
                replay_blocked=True,
            )

        provenance = ExecutionProvenance(
            schema_version="phios.execution_provenance.v0.8",
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            plan_revision=plan.revision,
            transition_index=binding.transition_index,
            source_state_id=binding.source_state_id,
            target_state_id=binding.target_state_id,
            action_binding_sha256=binding.binding_sha256,
        )
        try:
            execution = spine.run(
                binding.capability_id,
                dict(payload),
                governed_provenance=provenance,
            )
        except (KeyError, TypeError, ValueError) as exc:
            spine.ledger.release_binding_claim(binding.binding_sha256)
            raise ExecutionHandoffContractError(
                f"spine execution handoff failed before receipting: {exc}"
            ) from exc

        if execution.input_sha256 != binding.payload_sha256:
            raise ExecutionHandoffContractError(
                "spine execution payload digest diverged from action binding"
            )
        if execution.permissions_requested != list(binding.permissions_requested):
            raise ExecutionHandoffContractError(
                "spine permission request diverged from action binding"
            )
        if execution.governed_provenance != provenance:
            raise ExecutionHandoffContractError(
                "spine execution provenance diverged from action binding"
            )

        status, reason, binding_consumed = self._outcome(execution)
        if not binding_consumed:
            spine.ledger.release_binding_claim(binding.binding_sha256)
        return self._receipt(
            plan=plan,
            binding=binding,
            status=status,
            reason=reason,
            binding_consumed=binding_consumed,
            replay_blocked=False,
            execution=execution,
        )

    def _validate_inputs(
        self,
        plan: PlanState,
        binding: PlanActionBinding,
    ) -> None:
        try:
            self._plan_gate.validate_plan_state(plan)
            self._binder.validate_binding(binding)
        except (PlanAdoptionContractError, ActionBindingContractError) as exc:
            raise ExecutionHandoffContractError(str(exc)) from exc

    def _lease_scope(
        self,
        binding: PlanActionBinding,
        lease: ActionLease,
    ) -> str | None:
        if lease.capability_id != binding.capability_id:
            return "action_lease_capability_scope_mismatch"
        if lease.capability_version != binding.capability_version:
            return "action_lease_capability_version_scope_mismatch"
        if lease.payload_sha256 != binding.payload_sha256:
            return "action_lease_payload_scope_mismatch"
        if lease.effects_declared != binding.effects_declared:
            return "action_lease_effect_scope_mismatch"
        expected_permissions = tuple(
            sorted(set(binding.permissions_requested))
        )
        if lease.permissions_authorized != expected_permissions:
            return "action_lease_permission_scope_mismatch"
        return None

    def _held_with_lease(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        lease: ActionLease,
        reason: str,
        evaluation_reason: str,
        replay_blocked: bool = False,
    ) -> ExecutionHandoffReceipt:
        return self._attach_lease(
            self._held(
                plan=plan,
                binding=binding,
                reason=reason,
                replay_blocked=replay_blocked,
            ),
            lease=lease,
            lease_consumed=False,
            evaluation_reason=evaluation_reason,
        )

    def _attach_lease(
        self,
        receipt: ExecutionHandoffReceipt,
        *,
        lease: ActionLease,
        lease_consumed: bool,
        evaluation_reason: str,
    ) -> ExecutionHandoffReceipt:
        updated = replace(
            receipt,
            action_lease_sha256=lease.action_lease_sha256,
            lease_consumed=lease_consumed,
            lease_evaluation_reason=evaluation_reason,
            receipt_sha256="",
        )
        payload = updated.to_dict()
        payload.pop("receipt_sha256")
        return replace(
            updated,
            receipt_sha256=_payload_digest(payload),
        )

    def _current_plan_scope(
        self,
        plan: PlanState,
        binding: PlanActionBinding,
    ) -> str | None:
        if binding.plan_id != plan.plan_id:
            return "binding_plan_scope_mismatch"
        if binding.plan_state_sha256 != plan.state_sha256:
            return "binding_plan_state_scope_mismatch"
        if binding.plan_revision != plan.revision:
            return "binding_plan_revision_scope_mismatch"
        if (
            binding.transition_index < 0
            or binding.transition_index >= len(plan.path_ids) - 1
        ):
            return "binding_transition_not_in_current_plan"
        if plan.path_ids[binding.transition_index] != binding.source_state_id:
            return "binding_source_not_in_current_plan"
        if plan.path_ids[binding.transition_index + 1] != binding.target_state_id:
            return "binding_target_not_in_current_plan"
        return None

    def _outcome(
        self,
        execution: ExecutionReceipt,
    ) -> tuple[str, str, bool]:
        if execution.permission_status == "denied":
            return "DENIED", "spine_permission_denied", False
        if (
            execution.permission_status == "allowed"
            and execution.execution_status == "succeeded"
        ):
            return "SUCCEEDED", "spine_execution_succeeded", True
        if (
            execution.permission_status == "allowed"
            and execution.execution_status == "failed"
        ):
            return "FAILED", "spine_execution_failed", True
        raise ExecutionHandoffContractError(
            "spine returned an unsupported execution outcome"
        )

    def _held(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        reason: str,
        replay_blocked: bool = False,
    ) -> ExecutionHandoffReceipt:
        return self._receipt(
            plan=plan,
            binding=binding,
            status="HELD",
            reason=reason,
            binding_consumed=False,
            replay_blocked=replay_blocked,
            execution=None,
        )

    def _receipt(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        status: str,
        reason: str,
        binding_consumed: bool,
        replay_blocked: bool,
        execution: ExecutionReceipt | None,
    ) -> ExecutionHandoffReceipt:
        payload: dict[str, object] = {
            "schema": "phios.execution_handoff_receipt.v0.8",
            "status": status,
            "reason": reason,
            "plan_id": plan.plan_id,
            "plan_state_sha256": plan.state_sha256,
            "plan_revision": plan.revision,
            "transition_index": binding.transition_index,
            "source_state_id": binding.source_state_id,
            "target_state_id": binding.target_state_id,
            "capability_id": binding.capability_id,
            "payload_sha256": binding.payload_sha256,
            "action_binding_sha256": binding.binding_sha256,
            "binding_consumed": binding_consumed,
            "replay_blocked": replay_blocked,
            "spine_receipt_id": execution.receipt_id if execution else None,
            "spine_permission_status": (
                execution.permission_status if execution else None
            ),
            "spine_execution_status": (
                execution.execution_status if execution else None
            ),
            "gate_receipt_id": execution.gate_receipt_id if execution else None,
            "action_receipt_id": (
                execution.action_receipt_id if execution else None
            ),
            "mandala_status": execution.mandala_status if execution else None,
            "artifact_path": execution.artifact_path if execution else None,
            "artifact_sha256": execution.artifact_sha256 if execution else None,
            "action_lease_sha256": None,
            "lease_consumed": False,
            "lease_evaluation_reason": None,
            "action_authority": False,
            "execution_authority": False,
        }
        return ExecutionHandoffReceipt(
            schema="phios.execution_handoff_receipt.v0.8",
            status=status,
            reason=reason,
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            plan_revision=plan.revision,
            transition_index=binding.transition_index,
            source_state_id=binding.source_state_id,
            target_state_id=binding.target_state_id,
            capability_id=binding.capability_id,
            payload_sha256=binding.payload_sha256,
            action_binding_sha256=binding.binding_sha256,
            binding_consumed=binding_consumed,
            replay_blocked=replay_blocked,
            spine_receipt_id=execution.receipt_id if execution else None,
            spine_permission_status=(
                execution.permission_status if execution else None
            ),
            spine_execution_status=(
                execution.execution_status if execution else None
            ),
            gate_receipt_id=execution.gate_receipt_id if execution else None,
            action_receipt_id=(
                execution.action_receipt_id if execution else None
            ),
            mandala_status=execution.mandala_status if execution else None,
            artifact_path=execution.artifact_path if execution else None,
            artifact_sha256=execution.artifact_sha256 if execution else None,
            action_lease_sha256=None,
            lease_consumed=False,
            lease_evaluation_reason=None,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_payload_digest(payload),
        )


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
        raise ExecutionHandoffContractError(
            "execution handoff payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()
