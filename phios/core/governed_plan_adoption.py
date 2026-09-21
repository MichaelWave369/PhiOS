"""Governed plan adoption for PhiOS core reasoning v0.6.

A v0.5 REPLAN receipt is only a recommendation. v0.6 requires a narrowly
scoped external grant before that recommendation can become the next incumbent
plan state. Plan adoption never grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_replanning import GovernedReplanReceipt


class PlanAdoptionContractError(ValueError):
    """Raised when plan-adoption state or receipts are malformed."""


@dataclass(frozen=True, slots=True)
class PlanAdoptionGrant:
    """Externally issued authority scoped to one plan/replan/disposition tuple."""

    grant_id: str
    authority_source: str
    plan_id: str
    current_plan_sha256: str
    replan_receipt_sha256: str
    disposition: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.plan_adoption_grant.v0.6",
            "grant_id": self.grant_id,
            "authority_source": self.authority_source,
            "plan_id": self.plan_id,
            "current_plan_sha256": self.current_plan_sha256,
            "replan_receipt_sha256": self.replan_receipt_sha256,
            "disposition": self.disposition,
        }

    @property
    def grant_sha256(self) -> str:
        return _payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class PlanState:
    """Immutable incumbent plan state with no execution authority."""

    schema: str
    plan_id: str
    revision: int
    path_ids: tuple[str, ...]
    source_route_receipt_sha256: str
    source_replan_receipt_sha256: str | None
    parent_plan_sha256: str | None
    action_authority: bool
    execution_authority: bool
    state_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "revision": self.revision,
            "path_ids": list(self.path_ids),
            "source_route_receipt_sha256": self.source_route_receipt_sha256,
            "source_replan_receipt_sha256": self.source_replan_receipt_sha256,
            "parent_plan_sha256": self.parent_plan_sha256,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class PlanAdoptionReceipt:
    """Deterministic ADOPTED / REJECTED / HELD plan-governance receipt."""

    schema: str
    status: str
    reason: str
    requested_disposition: str
    plan_id: str
    prior_plan_sha256: str
    next_plan_sha256: str
    prior_revision: int
    next_revision: int
    replan_receipt_sha256: str
    replan_decision: str
    candidate_route_receipt_sha256: str
    candidate_path_ids: tuple[str, ...]
    grant_id: str | None
    grant_sha256: str | None
    authority_source: str | None
    grant_scope_valid: bool
    plan_changed: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "requested_disposition": self.requested_disposition,
            "plan_id": self.plan_id,
            "prior_plan_sha256": self.prior_plan_sha256,
            "next_plan_sha256": self.next_plan_sha256,
            "prior_revision": self.prior_revision,
            "next_revision": self.next_revision,
            "replan_receipt_sha256": self.replan_receipt_sha256,
            "replan_decision": self.replan_decision,
            "candidate_route_receipt_sha256": self.candidate_route_receipt_sha256,
            "candidate_path_ids": list(self.candidate_path_ids),
            "grant_id": self.grant_id,
            "grant_sha256": self.grant_sha256,
            "authority_source": self.authority_source,
            "grant_scope_valid": self.grant_scope_valid,
            "plan_changed": self.plan_changed,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedPlanAdoptionGate:
    """Apply explicit scoped plan-adoption authority without executing the plan."""

    def validate_plan_state(self, state: PlanState) -> None:
        """Validate an immutable plan state without changing it."""

        self._validate_plan_state(state)

    def initialize_plan(
        self,
        *,
        plan_id: str,
        route_receipt: FieldAwareRouteReceipt,
    ) -> PlanState:
        normalized_plan_id = plan_id.strip()
        if not normalized_plan_id:
            raise PlanAdoptionContractError("plan_id must be non-empty")
        _validate_route_receipt(route_receipt)
        if route_receipt.status != "found" or not route_receipt.path_ids:
            raise PlanAdoptionContractError(
                "initial plan requires a found route with path IDs"
            )
        return self._build_plan_state(
            plan_id=normalized_plan_id,
            revision=0,
            path_ids=route_receipt.path_ids,
            source_route_receipt_sha256=route_receipt.receipt_sha256,
            source_replan_receipt_sha256=None,
            parent_plan_sha256=None,
        )

    def apply(
        self,
        *,
        current_plan: PlanState,
        replan_receipt: GovernedReplanReceipt,
        requested_disposition: str,
        grant: PlanAdoptionGrant | None,
    ) -> tuple[PlanState, PlanAdoptionReceipt]:
        self._validate_plan_state(current_plan)
        _validate_replan_receipt(replan_receipt)
        disposition = _normalize_disposition(requested_disposition)

        if (
            replan_receipt.previous_route_receipt_sha256
            != current_plan.source_route_receipt_sha256
        ):
            return self._unchanged_receipt(
                current_plan=current_plan,
                replan_receipt=replan_receipt,
                disposition=disposition,
                grant=grant,
                status="HELD",
                reason="stale_replan_receipt",
                grant_scope_valid=False,
            )

        if replan_receipt.decision != "REPLAN":
            return self._unchanged_receipt(
                current_plan=current_plan,
                replan_receipt=replan_receipt,
                disposition=disposition,
                grant=grant,
                status="HELD",
                reason="replan_decision_not_adoptable",
                grant_scope_valid=False,
            )

        if (
            replan_receipt.candidate_status != "found"
            or not replan_receipt.candidate_path_ids
        ):
            raise PlanAdoptionContractError(
                "REPLAN receipt must contain a found candidate route"
            )

        scope_valid, scope_reason = self._grant_scope(
            current_plan=current_plan,
            replan_receipt=replan_receipt,
            disposition=disposition,
            grant=grant,
        )
        if not scope_valid:
            return self._unchanged_receipt(
                current_plan=current_plan,
                replan_receipt=replan_receipt,
                disposition=disposition,
                grant=grant,
                status="HELD",
                reason=scope_reason,
                grant_scope_valid=False,
            )

        if disposition == "HOLD":
            return self._unchanged_receipt(
                current_plan=current_plan,
                replan_receipt=replan_receipt,
                disposition=disposition,
                grant=grant,
                status="HELD",
                reason="authorized_hold",
                grant_scope_valid=True,
            )

        if disposition == "REJECT":
            return self._unchanged_receipt(
                current_plan=current_plan,
                replan_receipt=replan_receipt,
                disposition=disposition,
                grant=grant,
                status="REJECTED",
                reason="authorized_rejection",
                grant_scope_valid=True,
            )

        next_plan = self._build_plan_state(
            plan_id=current_plan.plan_id,
            revision=current_plan.revision + 1,
            path_ids=replan_receipt.candidate_path_ids,
            source_route_receipt_sha256=(
                replan_receipt.candidate_route_receipt_sha256
            ),
            source_replan_receipt_sha256=replan_receipt.receipt_sha256,
            parent_plan_sha256=current_plan.state_sha256,
        )
        receipt = self._build_receipt(
            status="ADOPTED",
            reason="authorized_replan_adopted",
            disposition=disposition,
            current_plan=current_plan,
            next_plan=next_plan,
            replan_receipt=replan_receipt,
            grant=grant,
            grant_scope_valid=True,
        )
        return next_plan, receipt

    def _grant_scope(
        self,
        *,
        current_plan: PlanState,
        replan_receipt: GovernedReplanReceipt,
        disposition: str,
        grant: PlanAdoptionGrant | None,
    ) -> tuple[bool, str]:
        if grant is None:
            return False, "adoption_authority_missing"

        grant_id = grant.grant_id.strip()
        authority_source = grant.authority_source.strip()
        plan_id = grant.plan_id.strip()
        grant_disposition = _normalize_disposition(grant.disposition)
        if not grant_id:
            raise PlanAdoptionContractError("grant_id must be non-empty")
        if not authority_source:
            raise PlanAdoptionContractError(
                "grant authority_source must be non-empty"
            )
        if not plan_id:
            raise PlanAdoptionContractError("grant plan_id must be non-empty")

        if plan_id != current_plan.plan_id:
            return False, "grant_plan_scope_mismatch"
        if grant.current_plan_sha256 != current_plan.state_sha256:
            return False, "grant_plan_state_scope_mismatch"
        if grant.replan_receipt_sha256 != replan_receipt.receipt_sha256:
            return False, "grant_replan_scope_mismatch"
        if grant_disposition != disposition:
            return False, "grant_disposition_scope_mismatch"
        return True, "grant_scope_valid"

    def _validate_plan_state(self, state: PlanState) -> None:
        if state.schema != "phios.plan_state.v0.6":
            raise PlanAdoptionContractError("unsupported plan state schema")
        if not state.plan_id.strip():
            raise PlanAdoptionContractError("plan state plan_id must be non-empty")
        if state.revision < 0:
            raise PlanAdoptionContractError(
                "plan state revision must be non-negative"
            )
        if not state.path_ids or any(not item.strip() for item in state.path_ids):
            raise PlanAdoptionContractError(
                "plan state must contain non-empty path IDs"
            )
        if state.action_authority is not False:
            raise PlanAdoptionContractError(
                "plan state cannot carry action authority"
            )
        if state.execution_authority is not False:
            raise PlanAdoptionContractError(
                "plan state cannot carry execution authority"
            )

        expected = self._plan_state_digest(
            plan_id=state.plan_id,
            revision=state.revision,
            path_ids=state.path_ids,
            source_route_receipt_sha256=state.source_route_receipt_sha256,
            source_replan_receipt_sha256=state.source_replan_receipt_sha256,
            parent_plan_sha256=state.parent_plan_sha256,
        )
        if expected != state.state_sha256:
            raise PlanAdoptionContractError(
                "plan state hash does not match state contents"
            )

    def _build_plan_state(
        self,
        *,
        plan_id: str,
        revision: int,
        path_ids: tuple[str, ...],
        source_route_receipt_sha256: str,
        source_replan_receipt_sha256: str | None,
        parent_plan_sha256: str | None,
    ) -> PlanState:
        digest = self._plan_state_digest(
            plan_id=plan_id,
            revision=revision,
            path_ids=path_ids,
            source_route_receipt_sha256=source_route_receipt_sha256,
            source_replan_receipt_sha256=source_replan_receipt_sha256,
            parent_plan_sha256=parent_plan_sha256,
        )
        return PlanState(
            schema="phios.plan_state.v0.6",
            plan_id=plan_id,
            revision=revision,
            path_ids=path_ids,
            source_route_receipt_sha256=source_route_receipt_sha256,
            source_replan_receipt_sha256=source_replan_receipt_sha256,
            parent_plan_sha256=parent_plan_sha256,
            action_authority=False,
            execution_authority=False,
            state_sha256=digest,
        )

    def _plan_state_digest(
        self,
        *,
        plan_id: str,
        revision: int,
        path_ids: tuple[str, ...],
        source_route_receipt_sha256: str,
        source_replan_receipt_sha256: str | None,
        parent_plan_sha256: str | None,
    ) -> str:
        payload: dict[str, object] = {
            "schema": "phios.plan_state.v0.6",
            "plan_id": plan_id,
            "revision": revision,
            "path_ids": list(path_ids),
            "source_route_receipt_sha256": source_route_receipt_sha256,
            "source_replan_receipt_sha256": source_replan_receipt_sha256,
            "parent_plan_sha256": parent_plan_sha256,
            "action_authority": False,
            "execution_authority": False,
        }
        return _payload_digest(payload)

    def _unchanged_receipt(
        self,
        *,
        current_plan: PlanState,
        replan_receipt: GovernedReplanReceipt,
        disposition: str,
        grant: PlanAdoptionGrant | None,
        status: str,
        reason: str,
        grant_scope_valid: bool,
    ) -> tuple[PlanState, PlanAdoptionReceipt]:
        receipt = self._build_receipt(
            status=status,
            reason=reason,
            disposition=disposition,
            current_plan=current_plan,
            next_plan=current_plan,
            replan_receipt=replan_receipt,
            grant=grant,
            grant_scope_valid=grant_scope_valid,
        )
        return current_plan, receipt

    def _build_receipt(
        self,
        *,
        status: str,
        reason: str,
        disposition: str,
        current_plan: PlanState,
        next_plan: PlanState,
        replan_receipt: GovernedReplanReceipt,
        grant: PlanAdoptionGrant | None,
        grant_scope_valid: bool,
    ) -> PlanAdoptionReceipt:
        grant_id = grant.grant_id.strip() if grant is not None else None
        authority_source = (
            grant.authority_source.strip() if grant is not None else None
        )
        grant_sha256 = grant.grant_sha256 if grant is not None else None
        plan_changed = next_plan.state_sha256 != current_plan.state_sha256

        payload: dict[str, object] = {
            "schema": "phios.plan_adoption_receipt.v0.6",
            "status": status,
            "reason": reason,
            "requested_disposition": disposition,
            "plan_id": current_plan.plan_id,
            "prior_plan_sha256": current_plan.state_sha256,
            "next_plan_sha256": next_plan.state_sha256,
            "prior_revision": current_plan.revision,
            "next_revision": next_plan.revision,
            "replan_receipt_sha256": replan_receipt.receipt_sha256,
            "replan_decision": replan_receipt.decision,
            "candidate_route_receipt_sha256": (
                replan_receipt.candidate_route_receipt_sha256
            ),
            "candidate_path_ids": list(replan_receipt.candidate_path_ids),
            "grant_id": grant_id,
            "grant_sha256": grant_sha256,
            "authority_source": authority_source,
            "grant_scope_valid": grant_scope_valid,
            "plan_changed": plan_changed,
            "action_authority": False,
            "execution_authority": False,
        }
        return PlanAdoptionReceipt(
            schema="phios.plan_adoption_receipt.v0.6",
            status=status,
            reason=reason,
            requested_disposition=disposition,
            plan_id=current_plan.plan_id,
            prior_plan_sha256=current_plan.state_sha256,
            next_plan_sha256=next_plan.state_sha256,
            prior_revision=current_plan.revision,
            next_revision=next_plan.revision,
            replan_receipt_sha256=replan_receipt.receipt_sha256,
            replan_decision=replan_receipt.decision,
            candidate_route_receipt_sha256=(
                replan_receipt.candidate_route_receipt_sha256
            ),
            candidate_path_ids=replan_receipt.candidate_path_ids,
            grant_id=grant_id,
            grant_sha256=grant_sha256,
            authority_source=authority_source,
            grant_scope_valid=grant_scope_valid,
            plan_changed=plan_changed,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_payload_digest(payload),
        )


def _normalize_disposition(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"ADOPT", "REJECT", "HOLD"}:
        raise PlanAdoptionContractError(
            "disposition must be ADOPT, REJECT, or HOLD"
        )
    return normalized


def _validate_route_receipt(receipt: FieldAwareRouteReceipt) -> None:
    if receipt.schema != "phios.field_aware_route_receipt.v0.4":
        raise PlanAdoptionContractError(
            "unsupported route receipt schema"
        )
    if receipt.action_authority is not False:
        raise PlanAdoptionContractError(
            "route receipt cannot carry action authority"
        )
    expected = _route_receipt_digest(receipt)
    if expected != receipt.receipt_sha256:
        raise PlanAdoptionContractError(
            "route receipt hash does not match receipt contents"
        )


def _validate_replan_receipt(receipt: GovernedReplanReceipt) -> None:
    if receipt.schema != "phios.governed_replan_receipt.v0.5":
        raise PlanAdoptionContractError(
            "unsupported replan receipt schema"
        )
    if receipt.action_authority is not False:
        raise PlanAdoptionContractError(
            "replan receipt cannot carry action authority"
        )
    expected = _replan_receipt_digest(receipt)
    if expected != receipt.receipt_sha256:
        raise PlanAdoptionContractError(
            "replan receipt hash does not match receipt contents"
        )


def _route_receipt_digest(receipt: FieldAwareRouteReceipt) -> str:
    payload: dict[str, object] = {
        "schema": receipt.schema,
        "status": receipt.status,
        "field_law_sha256": receipt.field_law_sha256,
        "field_state_sha256": receipt.field_state_sha256,
        "field_revision": receipt.field_revision,
        "bindings": [item.to_dict() for item in receipt.bindings],
        "path_receipt_sha256": receipt.path_receipt_sha256,
        "path_ids": list(receipt.path_ids),
        "total_cost": receipt.total_cost,
        "optimality_scope": receipt.optimality_scope,
        "action_authority": receipt.action_authority,
    }
    return _payload_digest(payload)


def _replan_receipt_digest(receipt: GovernedReplanReceipt) -> str:
    payload: dict[str, object] = {
        "schema": receipt.schema,
        "decision": receipt.decision,
        "reason": receipt.reason,
        "policy_id": receipt.policy_id,
        "policy_sha256": receipt.policy_sha256,
        "minimum_cost_improvement": receipt.minimum_cost_improvement,
        "previous_route_receipt_sha256": receipt.previous_route_receipt_sha256,
        "previous_field_state_sha256": receipt.previous_field_state_sha256,
        "current_field_state_sha256": receipt.current_field_state_sha256,
        "current_field_revision": receipt.current_field_revision,
        "incumbent_assessment_sha256": receipt.incumbent_assessment_sha256,
        "incumbent_path_ids": list(receipt.incumbent_path_ids),
        "incumbent_status": receipt.incumbent_status,
        "incumbent_current_cost": receipt.incumbent_current_cost,
        "candidate_route_receipt_sha256": receipt.candidate_route_receipt_sha256,
        "candidate_path_ids": list(receipt.candidate_path_ids),
        "candidate_status": receipt.candidate_status,
        "candidate_current_cost": receipt.candidate_current_cost,
        "route_changed": receipt.route_changed,
        "cost_improvement": receipt.cost_improvement,
        "comparison_scope": receipt.comparison_scope,
        "action_authority": receipt.action_authority,
    }
    return _payload_digest(payload)


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
        raise PlanAdoptionContractError(
            "plan adoption payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()
