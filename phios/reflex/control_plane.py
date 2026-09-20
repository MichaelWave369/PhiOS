"""PhiReflex v0.7 persistent runtime control plane.

This layer persists v0.5/v0.6 governance artifacts, ingests external activation
grants without issuing them, restores valid activation state after restart,
maintains a hash-chained local receipt ledger, and fails closed on corrupted or
mismatched runtime state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from phios.reflex.coordination import CrossProcessFileLock, runtime_locked
from phios.reflex.influence_adoption import (
    GovernedReflexInfluenceAdoptionGate,
    ReflexInfluencePolicyState,
)
from phios.reflex.models import ReflexInput
from phios.reflex.providers.base import ReflexProvider
from phios.reflex.runtime_influence import (
    GovernedReflexRuntimeInfluence,
    ReflexActivationGrant,
    ReflexActivationRequest,
    ReflexActivationState,
    ReflexRoutingInfluenceSignal,
)


class ReflexControlPlaneContractError(ValueError):
    """Raised when persisted Reflex runtime control state is malformed."""


@dataclass(frozen=True, slots=True)
class ReflexRuntimeLease:
    schema: str
    activation_state_sha256: str
    valid_through_epoch: int
    set_at_evaluation_epoch: int
    lease_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "activation_state_sha256": self.activation_state_sha256,
            "valid_through_epoch": self.valid_through_epoch,
            "set_at_evaluation_epoch": self.set_at_evaluation_epoch,
            "lease_sha256": self.lease_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexControlPlaneReceipt:
    schema: str
    status: str
    reason: str
    evaluation_epoch: int
    policy_state_sha256: str | None
    activation_state_sha256: str | None
    related_sha256: str | None
    privilege_expanded: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "evaluation_epoch": self.evaluation_epoch,
            "policy_state_sha256": self.policy_state_sha256,
            "activation_state_sha256": self.activation_state_sha256,
            "related_sha256": self.related_sha256,
            "privilege_expanded": self.privilege_expanded,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class ReflexRuntimeControlPlane:
    """Crash-safe persistence and operator control around v0.6 runtime influence."""

    def __init__(self, *, root: Path | None = None) -> None:
        env_root = os.getenv("PHIOS_REFLEX_HOME", "").strip()
        self.root = (
            root
            if root is not None
            else Path(env_root)
            if env_root
            else Path.home() / ".phios" / "reflex"
        )
        self.runtime = GovernedReflexRuntimeInfluence()
        self.policy_gate = GovernedReflexInfluenceAdoptionGate()
        self._runtime_lock = CrossProcessFileLock(self.root / "control.lock")

    @property
    def policy_path(self) -> Path:
        return self.root / "policy.json"

    @property
    def activation_path(self) -> Path:
        return self.root / "activation.json"

    @property
    def lease_path(self) -> Path:
        return self.root / "lease.json"

    @property
    def grants_dir(self) -> Path:
        return self.root / "grants"

    @property
    def ledger_path(self) -> Path:
        return self.root / "ledger.json"

    @property
    def quarantine_dir(self) -> Path:
        return self.root / "quarantine"

    @runtime_locked
    def ingest_policy_payload(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self.recover(evaluation_epoch=epoch)
        policy = policy_from_payload(payload)
        self.policy_gate.validate_policy_state(policy)

        current_activation = self._load_activation_optional()
        if (
            current_activation is not None
            and current_activation.routing_influence_active
            and current_activation.policy_state_sha256 != policy.state_sha256
        ):
            raise ReflexControlPlaneContractError(
                "deactivate live Reflex influence before replacing policy"
            )

        _atomic_write_json(self.policy_path, policy.to_dict())
        if (
            current_activation is not None
            and not current_activation.routing_influence_active
            and current_activation.policy_state_sha256 != policy.state_sha256
        ):
            self._quarantine(self.activation_path)
            self._remove_file(self.lease_path)

        receipt = self._control_receipt(
            status="POLICY_STORED",
            reason="validated_v0_5_policy_persisted",
            evaluation_epoch=epoch,
            policy_sha=policy.state_sha256,
            activation_sha=None,
            related_sha=policy.readiness_receipt_sha256,
        )
        self._append_ledger("control", epoch, receipt.to_dict())
        return {
            "ok": True,
            "policy": policy.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def ingest_grant_payload(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        grant = activation_grant_from_payload(payload)
        self.runtime.validate_activation_grant(grant)
        _safe_id(grant.grant_id)
        path = self.grants_dir / f"{grant.grant_id}.json"
        if path.exists():
            existing = activation_grant_from_payload(_read_object(path))
            if existing.grant_sha256 != grant.grant_sha256:
                raise ReflexControlPlaneContractError(
                    "grant_id already exists with different contents"
                )
            receipt = self._control_receipt(
                status="GRANT_ALREADY_PRESENT",
                reason="exact_activation_grant_already_ingested",
                evaluation_epoch=epoch,
                policy_sha=grant.policy_state_sha256,
                activation_sha=grant.current_activation_sha256,
                related_sha=grant.grant_sha256,
            )
            self._append_ledger("control", epoch, receipt.to_dict())
            return {
                "ok": True,
                "idempotent": True,
                "grant_sha256": grant.grant_sha256,
                "receipt": receipt.to_dict(),
            }

        _atomic_write_json(path, grant.to_payload())
        receipt = self._control_receipt(
            status="GRANT_INGESTED",
            reason="external_activation_grant_validated_and_persisted",
            evaluation_epoch=epoch,
            policy_sha=grant.policy_state_sha256,
            activation_sha=grant.current_activation_sha256,
            related_sha=grant.grant_sha256,
        )
        self._append_ledger("control", epoch, receipt.to_dict())
        return {
            "ok": True,
            "idempotent": False,
            "grant_sha256": grant.grant_sha256,
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def activate(
        self,
        *,
        request: ReflexActivationRequest,
        grant_id: str,
        evaluation_epoch: int,
        lease_until_epoch: int | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self.recover(evaluation_epoch=epoch)
        policy = self._require_policy()
        current = self._load_activation_optional()
        grant = self._require_grant(grant_id)
        existing_lease = self._load_lease_optional()
        requested_deadline = (
            _epoch(lease_until_epoch)
            if lease_until_epoch is not None
            else None
        )
        if requested_deadline is not None and requested_deadline <= epoch:
            raise ReflexControlPlaneContractError(
                "lease_until_epoch must be greater than evaluation_epoch"
            )
        if (
            existing_lease is not None
            and requested_deadline is not None
            and requested_deadline > existing_lease.valid_through_epoch
        ):
            raise ReflexControlPlaneContractError(
                "v0.7 lease may be shortened but not extended"
            )

        next_state, activation_receipt = self.runtime.activate(
            policy=policy,
            request=request,
            grant=grant,
            current_activation=current,
        )
        if next_state is not None and next_state.state_sha256 != (
            current.state_sha256 if current is not None else None
        ):
            _atomic_write_json(self.activation_path, next_state.to_dict())

        self._append_ledger(
            "activation",
            epoch,
            activation_receipt.to_dict(),
        )

        lease: ReflexRuntimeLease | None = None
        if next_state is not None and activation_receipt.status == "ACTIVATED":
            inherited_deadline = (
                existing_lease.valid_through_epoch
                if existing_lease is not None
                else None
            )
            deadline = (
                requested_deadline
                if requested_deadline is not None
                else inherited_deadline
            )
            if deadline is not None:
                lease = _build_lease(
                    activation_state_sha256=next_state.state_sha256,
                    valid_through_epoch=deadline,
                    set_at_evaluation_epoch=epoch,
                )
                _atomic_write_json(self.lease_path, lease.to_dict())
            else:
                self._remove_file(self.lease_path)

        return {
            "ok": activation_receipt.status == "ACTIVATED",
            "activation": (
                next_state.to_dict() if next_state is not None else None
            ),
            "activation_receipt": activation_receipt.to_dict(),
            "lease": lease.to_dict() if lease is not None else None,
        }

    @runtime_locked
    def attach_or_shorten_lease(
        self,
        *,
        valid_through_epoch: int,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        deadline = _epoch(valid_through_epoch)
        self.recover(evaluation_epoch=epoch)
        policy = self._require_policy()
        state = self._require_activation()
        if not state.routing_influence_active:
            raise ReflexControlPlaneContractError(
                "cannot attach lease to inactive runtime influence"
            )
        current = self._load_lease_optional()
        if current is not None and deadline > current.valid_through_epoch:
            raise ReflexControlPlaneContractError(
                "v0.7 lease may be shortened but not extended"
            )
        if deadline <= epoch:
            result = self.deactivate(
                reason="lease_expired_or_immediate",
                evaluation_epoch=epoch,
            )
            return {
                "ok": True,
                "lease": None,
                "deactivation": result,
            }

        lease = _build_lease(
            activation_state_sha256=state.state_sha256,
            valid_through_epoch=deadline,
            set_at_evaluation_epoch=epoch,
        )
        _atomic_write_json(self.lease_path, lease.to_dict())
        receipt = self._control_receipt(
            status="LEASE_ATTACHED",
            reason="privilege_duration_restricted",
            evaluation_epoch=epoch,
            policy_sha=policy.state_sha256,
            activation_sha=state.state_sha256,
            related_sha=lease.lease_sha256,
        )
        self._append_ledger("control", epoch, receipt.to_dict())
        return {
            "ok": True,
            "lease": lease.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def renew_lease_authorized(
        self,
        *,
        valid_through_epoch: int,
        evaluation_epoch: int,
        authorization_sha256: str,
    ) -> dict[str, Any]:
        """Extend a lease only when an upstream authenticated authority binds it."""

        epoch = _epoch(evaluation_epoch)
        deadline = _epoch(valid_through_epoch)
        _require_sha256(authorization_sha256, "authorization_sha256")
        self.recover(evaluation_epoch=epoch)
        policy = self._require_policy()
        state = self._require_activation()
        if not state.routing_influence_active:
            raise ReflexControlPlaneContractError(
                "cannot renew lease for inactive runtime influence"
            )
        current = self._load_lease_optional()
        if current is None:
            raise ReflexControlPlaneContractError(
                "authorized renewal requires an existing lease"
            )
        if deadline <= current.valid_through_epoch:
            raise ReflexControlPlaneContractError(
                "authorized lease renewal must extend the current deadline"
            )
        if deadline <= epoch:
            raise ReflexControlPlaneContractError(
                "authorized lease renewal must remain in the future"
            )

        lease = _build_lease(
            activation_state_sha256=state.state_sha256,
            valid_through_epoch=deadline,
            set_at_evaluation_epoch=epoch,
        )
        _atomic_write_json(self.lease_path, lease.to_dict())
        receipt = self._control_receipt(
            status="LEASE_RENEWED",
            reason="upstream_authenticated_authority_extended_runtime_lease",
            evaluation_epoch=epoch,
            policy_sha=policy.state_sha256,
            activation_sha=state.state_sha256,
            related_sha=authorization_sha256,
        )
        self._append_ledger("authority", epoch, receipt.to_dict())
        return {
            "ok": True,
            "lease": lease.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def deactivate(
        self,
        *,
        reason: str,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self.recover(evaluation_epoch=epoch)
        policy = self._load_policy_optional()
        state = self._load_activation_optional()
        if policy is None or state is None:
            receipt = self._control_receipt(
                status="INACTIVE",
                reason="no_persisted_active_runtime",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256 if policy else None,
                activation_sha=state.state_sha256 if state else None,
                related_sha=None,
            )
            self._append_ledger("control", epoch, receipt.to_dict())
            return {"ok": True, "activation": None, "receipt": receipt.to_dict()}

        next_state, activation_receipt = self.runtime.deactivate(
            policy=policy,
            state=state,
            reason=reason,
        )
        _atomic_write_json(self.activation_path, next_state.to_dict())
        self._remove_file(self.lease_path)
        self._append_ledger(
            "activation",
            epoch,
            activation_receipt.to_dict(),
        )
        return {
            "ok": True,
            "activation": next_state.to_dict(),
            "activation_receipt": activation_receipt.to_dict(),
        }

    @runtime_locked
    def evaluate_active(
        self,
        *,
        reflex_input: ReflexInput,
        baseline_provider: ReflexProvider,
        influence_provider: ReflexProvider,
        evaluation_epoch: int,
    ) -> tuple[ReflexRoutingInfluenceSignal | None, dict[str, Any]]:
        epoch = _epoch(evaluation_epoch)
        self.recover(evaluation_epoch=epoch)
        policy = self._load_policy_optional()
        state = self._load_activation_optional()
        if (
            policy is None
            or state is None
            or not state.routing_influence_active
        ):
            return None, {
                "status": "INACTIVE",
                "routing_influence_active": False,
            }

        lease = self._load_lease_optional()
        next_state, signal, runtime_receipt = self.runtime.evaluate(
            policy=policy,
            state=state,
            reflex_input=reflex_input,
            baseline_provider=baseline_provider,
            influence_provider=influence_provider,
        )
        if next_state.state_sha256 != state.state_sha256:
            _atomic_write_json(self.activation_path, next_state.to_dict())
            if lease is not None and next_state.routing_influence_active:
                carried = _build_lease(
                    activation_state_sha256=next_state.state_sha256,
                    valid_through_epoch=lease.valid_through_epoch,
                    set_at_evaluation_epoch=lease.set_at_evaluation_epoch,
                )
                _atomic_write_json(self.lease_path, carried.to_dict())
            elif not next_state.routing_influence_active:
                self._remove_file(self.lease_path)

        self._append_ledger("runtime", epoch, runtime_receipt.to_dict())
        return signal, {
            "status": runtime_receipt.status,
            "routing_influence_active": next_state.routing_influence_active,
            "runtime_receipt": runtime_receipt.to_dict(),
            "signal": signal.to_dict() if signal is not None else None,
        }

    @runtime_locked
    def status(self, *, evaluation_epoch: int) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        recovery = self.recover(evaluation_epoch=epoch)
        policy = self._load_policy_optional()
        activation = self._load_activation_optional()
        lease = self._load_lease_optional()
        grants = (
            sorted(path.stem for path in self.grants_dir.glob("*.json"))
            if self.grants_dir.exists()
            else []
        )
        ledger = self._load_ledger()
        return {
            "ok": True,
            "evaluation_epoch": epoch,
            "recovery": recovery,
            "policy": policy.to_dict() if policy is not None else None,
            "activation": (
                activation.to_dict() if activation is not None else None
            ),
            "lease": lease.to_dict() if lease is not None else None,
            "grant_ids": grants,
            "ledger_entries": len(ledger),
            "routing_influence_active": bool(
                activation is not None
                and activation.routing_influence_active
            ),
        }

    @runtime_locked
    def ledger(self, *, tail: int | None = None) -> list[dict[str, Any]]:
        entries = self._load_ledger()
        if tail is None:
            return entries
        if tail < 0:
            raise ReflexControlPlaneContractError(
                "ledger tail must be non-negative"
            )
        return entries[-tail:] if tail else []

    @runtime_locked
    def recover(self, *, evaluation_epoch: int) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        ledger_reset = False
        try:
            self._load_ledger()
        except ReflexControlPlaneContractError:
            self._quarantine(self.ledger_path)
            ledger_reset = True

        try:
            policy = self._load_policy_optional()
        except ReflexControlPlaneContractError:
            related = self._quarantine(self.policy_path)
            self._quarantine(self.activation_path)
            self._quarantine(self.lease_path)
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="invalid_policy_state_quarantined",
                evaluation_epoch=epoch,
                policy_sha=None,
                activation_sha=None,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "invalid_policy_state_quarantined",
                "ledger_reset": ledger_reset,
            }

        try:
            activation = self._load_activation_optional()
        except ReflexControlPlaneContractError:
            related = self._quarantine(self.activation_path)
            self._quarantine(self.lease_path)
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="invalid_activation_state_quarantined",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256 if policy else None,
                activation_sha=None,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "invalid_activation_state_quarantined",
                "ledger_reset": ledger_reset,
            }

        if activation is not None and policy is None:
            related = self._quarantine(self.activation_path)
            self._quarantine(self.lease_path)
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="activation_without_policy_quarantined",
                evaluation_epoch=epoch,
                policy_sha=None,
                activation_sha=activation.state_sha256,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "activation_without_policy_quarantined",
                "ledger_reset": ledger_reset,
            }

        if (
            activation is not None
            and policy is not None
            and activation.policy_state_sha256 != policy.state_sha256
        ):
            related = self._quarantine(self.activation_path)
            self._quarantine(self.lease_path)
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="policy_activation_scope_mismatch",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256,
                activation_sha=activation.state_sha256,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "policy_activation_scope_mismatch",
                "ledger_reset": ledger_reset,
            }

        if activation is None:
            if self.lease_path.exists():
                self._quarantine(self.lease_path)
            return {
                "status": "INACTIVE",
                "reason": "no_activation_state",
                "ledger_reset": ledger_reset,
            }

        try:
            lease = self._load_lease_optional()
        except ReflexControlPlaneContractError:
            related = self._quarantine(self.lease_path)
            if activation.routing_influence_active and policy is not None:
                next_state, activation_receipt = self.runtime.deactivate(
                    policy=policy,
                    state=activation,
                    reason="invalid_lease_fail_closed",
                )
                _atomic_write_json(self.activation_path, next_state.to_dict())
                self._append_ledger(
                    "activation",
                    epoch,
                    activation_receipt.to_dict(),
                )
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="invalid_lease_quarantined",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256 if policy else None,
                activation_sha=activation.state_sha256,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "invalid_lease_quarantined",
                "ledger_reset": ledger_reset,
            }

        if lease is not None and lease.activation_state_sha256 != activation.state_sha256:
            related = self._quarantine(self.lease_path)
            if activation.routing_influence_active and policy is not None:
                next_state, activation_receipt = self.runtime.deactivate(
                    policy=policy,
                    state=activation,
                    reason="lease_state_mismatch_fail_closed",
                )
                _atomic_write_json(self.activation_path, next_state.to_dict())
                self._append_ledger(
                    "activation",
                    epoch,
                    activation_receipt.to_dict(),
                )
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="lease_activation_scope_mismatch",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256 if policy else None,
                activation_sha=activation.state_sha256,
                related_sha=related,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "lease_activation_scope_mismatch",
                "ledger_reset": ledger_reset,
            }

        if (
            lease is not None
            and activation.routing_influence_active
            and epoch >= lease.valid_through_epoch
            and policy is not None
        ):
            next_state, activation_receipt = self.runtime.deactivate(
                policy=policy,
                state=activation,
                reason="runtime_lease_expired",
            )
            _atomic_write_json(self.activation_path, next_state.to_dict())
            self._remove_file(self.lease_path)
            self._append_ledger(
                "activation",
                epoch,
                activation_receipt.to_dict(),
            )
            receipt = self._control_receipt(
                status="LEASE_EXPIRED",
                reason="runtime_privilege_collapsed_at_lease_deadline",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256,
                activation_sha=next_state.state_sha256,
                related_sha=lease.lease_sha256,
            )
            self._append_ledger("control", epoch, receipt.to_dict())
            return {
                "status": "LEASE_EXPIRED",
                "reason": "runtime_privilege_collapsed_at_lease_deadline",
                "ledger_reset": ledger_reset,
            }

        if ledger_reset and activation.routing_influence_active and policy is not None:
            next_state, activation_receipt = self.runtime.deactivate(
                policy=policy,
                state=activation,
                reason="runtime_ledger_integrity_lost",
            )
            _atomic_write_json(self.activation_path, next_state.to_dict())
            self._remove_file(self.lease_path)
            self._append_ledger(
                "activation",
                epoch,
                activation_receipt.to_dict(),
            )
            receipt = self._control_receipt(
                status="RECOVERY_ROLLBACK",
                reason="ledger_integrity_loss_collapsed_privilege",
                evaluation_epoch=epoch,
                policy_sha=policy.state_sha256,
                activation_sha=next_state.state_sha256,
                related_sha=None,
            )
            self._append_ledger("recovery", epoch, receipt.to_dict())
            return {
                "status": "RECOVERY_ROLLBACK",
                "reason": "ledger_integrity_loss_collapsed_privilege",
                "ledger_reset": True,
            }

        return {
            "status": (
                "ACTIVE"
                if activation.routing_influence_active
                else "INACTIVE"
            ),
            "reason": "persisted_runtime_state_valid",
            "ledger_reset": ledger_reset,
        }

    def _load_policy_optional(self) -> ReflexInfluencePolicyState | None:
        if not self.policy_path.exists():
            return None
        policy = policy_from_payload(_read_object(self.policy_path))
        self.policy_gate.validate_policy_state(policy)
        return policy

    def _load_activation_optional(self) -> ReflexActivationState | None:
        if not self.activation_path.exists():
            return None
        state = activation_state_from_payload(_read_object(self.activation_path))
        self.runtime.validate_activation_state(state)
        return state

    def _load_lease_optional(self) -> ReflexRuntimeLease | None:
        if not self.lease_path.exists():
            return None
        lease = lease_from_payload(_read_object(self.lease_path))
        _validate_lease(lease)
        return lease

    def _require_policy(self) -> ReflexInfluencePolicyState:
        policy = self._load_policy_optional()
        if policy is None:
            raise ReflexControlPlaneContractError(
                "no persisted v0.5 influence policy"
            )
        return policy

    def _require_activation(self) -> ReflexActivationState:
        state = self._load_activation_optional()
        if state is None:
            raise ReflexControlPlaneContractError(
                "no persisted v0.6 activation state"
            )
        return state

    def _require_grant(self, grant_id: str) -> ReflexActivationGrant:
        _safe_id(grant_id)
        path = self.grants_dir / f"{grant_id}.json"
        if not path.exists():
            raise ReflexControlPlaneContractError(
                f"activation grant {grant_id!r} is not ingested"
            )
        grant = activation_grant_from_payload(_read_object(path))
        self.runtime.validate_activation_grant(grant)
        return grant

    @runtime_locked
    def append_audit_receipt(
        self,
        *,
        kind: str,
        evaluation_epoch: int,
        receipt: Mapping[str, Any],
    ) -> None:
        """Append a non-authorizing external governance receipt."""

        normalized_kind = kind.strip()
        if normalized_kind not in {
            "authority",
            "revocation",
            "coordination",
            "lifecycle",
            "attestation",
            "usage",
            "manifest",
            "lease",
            "replication",
        }:
            raise ReflexControlPlaneContractError(
                "unsupported external audit receipt kind"
            )
        self._append_ledger(
            normalized_kind,
            _epoch(evaluation_epoch),
            receipt,
        )

    def _append_ledger(
        self,
        kind: str,
        evaluation_epoch: int,
        receipt: Mapping[str, Any],
    ) -> None:
        entries = self._load_ledger()
        previous = (
            str(entries[-1]["entry_sha256"]) if entries else None
        )
        payload: dict[str, object] = {
            "sequence": len(entries) + 1,
            "kind": kind,
            "evaluation_epoch": evaluation_epoch,
            "previous_entry_sha256": previous,
            "receipt": dict(receipt),
        }
        entry = dict(payload)
        entry["entry_sha256"] = _digest(payload)
        entries.append(entry)
        _atomic_write_json(self.ledger_path, entries)

    def _load_ledger(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        raw = _read_json(self.ledger_path)
        if not isinstance(raw, list):
            raise ReflexControlPlaneContractError(
                "runtime ledger must be a list"
            )
        previous: str | None = None
        result: list[dict[str, Any]] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                raise ReflexControlPlaneContractError(
                    "runtime ledger entry must be an object"
                )
            entry = dict(item)
            if entry.get("sequence") != index:
                raise ReflexControlPlaneContractError(
                    "runtime ledger sequence is invalid"
                )
            if entry.get("previous_entry_sha256") != previous:
                raise ReflexControlPlaneContractError(
                    "runtime ledger hash chain is broken"
                )
            digest = str(entry.pop("entry_sha256", ""))
            _require_sha256(digest, "entry_sha256")
            if _digest(entry) != digest:
                raise ReflexControlPlaneContractError(
                    "runtime ledger entry hash does not match contents"
                )
            item_with_sha = dict(entry)
            item_with_sha["entry_sha256"] = digest
            result.append(item_with_sha)
            previous = digest
        return result

    def _control_receipt(
        self,
        *,
        status: str,
        reason: str,
        evaluation_epoch: int,
        policy_sha: str | None,
        activation_sha: str | None,
        related_sha: str | None,
    ) -> ReflexControlPlaneReceipt:
        payload: dict[str, object] = {
            "schema": "phios.reflex_control_plane_receipt.v0.7",
            "status": status,
            "reason": reason,
            "evaluation_epoch": evaluation_epoch,
            "policy_state_sha256": policy_sha,
            "activation_state_sha256": activation_sha,
            "related_sha256": related_sha,
            "privilege_expanded": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexControlPlaneReceipt(
            schema="phios.reflex_control_plane_receipt.v0.7",
            status=status,
            reason=reason,
            evaluation_epoch=evaluation_epoch,
            policy_state_sha256=policy_sha,
            activation_state_sha256=activation_sha,
            related_sha256=related_sha,
            privilege_expanded=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )

    def _quarantine(self, path: Path) -> str | None:
        if not path.exists():
            return None
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        target = self.quarantine_dir / f"{path.name}.{digest}.invalid"
        os.replace(path, target)
        return digest

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def policy_from_payload(
    payload: Mapping[str, Any],
) -> ReflexInfluencePolicyState:
    if payload.get("schema") != "phios.reflex_influence_policy_state.v0.5":
        raise ReflexControlPlaneContractError(
            "unsupported influence policy schema"
        )
    return ReflexInfluencePolicyState(
        schema=str(payload["schema"]),
        policy_id=str(payload.get("policy_id", "")),
        revision=_integer(payload.get("revision"), "revision"),
        readiness_receipt_sha256=str(
            payload.get("readiness_receipt_sha256", "")
        ),
        candidate_provider=str(payload.get("candidate_provider", "")),
        candidate_models=_string_tuple(
            payload.get("candidate_models"),
            "candidate_models",
        ),
        allowed_dimensions=_string_tuple(
            payload.get("allowed_dimensions"),
            "allowed_dimensions",
        ),
        max_influence_weight=_number(
            payload.get("max_influence_weight"),
            "max_influence_weight",
        ),
        rollback_on_provider_unavailable=_boolean(
            payload.get("rollback_on_provider_unavailable"),
            "rollback_on_provider_unavailable",
        ),
        max_consecutive_provider_errors=_integer(
            payload.get("max_consecutive_provider_errors"),
            "max_consecutive_provider_errors",
        ),
        parent_policy_sha256=_optional_string(
            payload.get("parent_policy_sha256")
        ),
        routing_influence_active=_boolean(
            payload.get("routing_influence_active"),
            "routing_influence_active",
        ),
        runtime_activation_authority=_boolean(
            payload.get("runtime_activation_authority"),
            "runtime_activation_authority",
        ),
        promotion_authority=_boolean(
            payload.get("promotion_authority"),
            "promotion_authority",
        ),
        action_authority=_boolean(
            payload.get("action_authority"),
            "action_authority",
        ),
        execution_authority=_boolean(
            payload.get("execution_authority"),
            "execution_authority",
        ),
        state_sha256=str(payload.get("state_sha256", "")),
    )


def activation_state_from_payload(
    payload: Mapping[str, Any],
) -> ReflexActivationState:
    if payload.get("schema") != "phios.reflex_activation_state.v0.6":
        raise ReflexControlPlaneContractError(
            "unsupported activation state schema"
        )
    return ReflexActivationState(
        schema=str(payload["schema"]),
        activation_id=str(payload.get("activation_id", "")),
        revision=_integer(payload.get("revision"), "revision"),
        policy_state_sha256=str(payload.get("policy_state_sha256", "")),
        provider=str(payload.get("provider", "")),
        models=_string_tuple(payload.get("models"), "models"),
        routing_surface=str(payload.get("routing_surface", "")),
        allowed_dimensions=_string_tuple(
            payload.get("allowed_dimensions"),
            "allowed_dimensions",
        ),
        influence_weight=_number(
            payload.get("influence_weight"),
            "influence_weight",
        ),
        consecutive_provider_errors=_integer(
            payload.get("consecutive_provider_errors"),
            "consecutive_provider_errors",
        ),
        parent_activation_sha256=_optional_string(
            payload.get("parent_activation_sha256")
        ),
        activated_by_grant_sha256=str(
            payload.get("activated_by_grant_sha256", "")
        ),
        routing_influence_active=_boolean(
            payload.get("routing_influence_active"),
            "routing_influence_active",
        ),
        routing_influence_authority=_boolean(
            payload.get("routing_influence_authority"),
            "routing_influence_authority",
        ),
        promotion_authority=_boolean(
            payload.get("promotion_authority"),
            "promotion_authority",
        ),
        action_authority=_boolean(
            payload.get("action_authority"),
            "action_authority",
        ),
        execution_authority=_boolean(
            payload.get("execution_authority"),
            "execution_authority",
        ),
        state_sha256=str(payload.get("state_sha256", "")),
    )


def activation_grant_from_payload(
    payload: Mapping[str, Any],
) -> ReflexActivationGrant:
    if payload.get("schema") != "phios.reflex_activation_grant.v0.6":
        raise ReflexControlPlaneContractError(
            "unsupported activation grant schema"
        )
    return ReflexActivationGrant(
        grant_id=str(payload.get("grant_id", "")),
        authority_source=str(payload.get("authority_source", "")),
        policy_state_sha256=str(payload.get("policy_state_sha256", "")),
        current_activation_sha256=_optional_string(
            payload.get("current_activation_sha256")
        ),
        activation_request_sha256=str(
            payload.get("activation_request_sha256", "")
        ),
        disposition=str(payload.get("disposition", "")),
    )


def activation_request_from_payload(
    payload: Mapping[str, Any],
) -> ReflexActivationRequest:
    if payload.get("schema") != "phios.reflex_activation_request.v0.6":
        raise ReflexControlPlaneContractError(
            "unsupported activation request schema"
        )
    return ReflexActivationRequest(
        provider=str(payload.get("provider", "")),
        models=_string_tuple(payload.get("models"), "models"),
        routing_surface=str(payload.get("routing_surface", "")),
        allowed_dimensions=_string_tuple(
            payload.get("allowed_dimensions"),
            "allowed_dimensions",
        ),
        influence_weight=_number(
            payload.get("influence_weight"),
            "influence_weight",
        ),
    )


def lease_from_payload(payload: Mapping[str, Any]) -> ReflexRuntimeLease:
    if payload.get("schema") != "phios.reflex_runtime_lease.v0.7":
        raise ReflexControlPlaneContractError(
            "unsupported runtime lease schema"
        )
    return ReflexRuntimeLease(
        schema=str(payload["schema"]),
        activation_state_sha256=str(
            payload.get("activation_state_sha256", "")
        ),
        valid_through_epoch=_integer(
            payload.get("valid_through_epoch"),
            "valid_through_epoch",
        ),
        set_at_evaluation_epoch=_integer(
            payload.get("set_at_evaluation_epoch"),
            "set_at_evaluation_epoch",
        ),
        lease_sha256=str(payload.get("lease_sha256", "")),
    )


def _build_lease(
    *,
    activation_state_sha256: str,
    valid_through_epoch: int,
    set_at_evaluation_epoch: int,
) -> ReflexRuntimeLease:
    payload: dict[str, object] = {
        "schema": "phios.reflex_runtime_lease.v0.7",
        "activation_state_sha256": activation_state_sha256,
        "valid_through_epoch": valid_through_epoch,
        "set_at_evaluation_epoch": set_at_evaluation_epoch,
    }
    return ReflexRuntimeLease(
        schema="phios.reflex_runtime_lease.v0.7",
        activation_state_sha256=activation_state_sha256,
        valid_through_epoch=valid_through_epoch,
        set_at_evaluation_epoch=set_at_evaluation_epoch,
        lease_sha256=_digest(payload),
    )


def _validate_lease(lease: ReflexRuntimeLease) -> None:
    _require_sha256(
        lease.activation_state_sha256,
        "activation_state_sha256",
    )
    _epoch(lease.valid_through_epoch)
    _epoch(lease.set_at_evaluation_epoch)
    payload = lease.to_dict()
    digest = str(payload.pop("lease_sha256"))
    _require_sha256(digest, "lease_sha256")
    if _digest(payload) != digest:
        raise ReflexControlPlaneContractError(
            "runtime lease hash does not match contents"
        )


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReflexControlPlaneContractError(
            f"invalid persisted JSON: {path.name}"
        ) from exc


def _read_object(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ReflexControlPlaneContractError(
            f"{path.name} must contain a JSON object"
        )
    return dict(value)


def _safe_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", normalized):
        raise ReflexControlPlaneContractError(
            "grant_id contains unsupported characters"
        )
    return normalized


def _epoch(value: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexControlPlaneContractError(
            "evaluation epoch must be a non-negative integer"
        )
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReflexControlPlaneContractError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReflexControlPlaneContractError(f"{label} must be numeric")
    number = float(value)
    if not (number == number and abs(number) != float("inf")):
        raise ReflexControlPlaneContractError(f"{label} must be finite")
    return number


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ReflexControlPlaneContractError(f"{label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReflexControlPlaneContractError(f"{label} must be a list")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise ReflexControlPlaneContractError(
            f"{label} cannot contain empty strings"
        )
    return result


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReflexControlPlaneContractError(
            "optional digest must be string or null"
        )
    return value


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexControlPlaneContractError(
            f"{label} must be a SHA-256 hex digest"
        )
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexControlPlaneContractError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc


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
        raise ReflexControlPlaneContractError(
            "control-plane payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
