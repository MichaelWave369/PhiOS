"""Lease-only Ghost-Walk execution handoff for Macro Runtime v0.35.

The public execution input is exactly one ActionLease identity. The service
recovers every executable detail from trusted PhiOS custody, revalidates the
current binding/policy/enforcement/authority state, atomically claims the
single-use lease, and delegates the exact stored payload through PhiOS Spine.

No caller may provide or replace a capability, payload, permission, effect,
target, enforcement rule, authority epoch, or lease field.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Mapping

from phios.action_lease import ActionLeaseContractError, evaluate_action_lease
from phios.authority_epoch import AuthorityEpoch, AuthorityEpochContractError
from phios.enforcement_profile import (
    EnforcementProfile,
    EnforcementProfileContractError,
)
from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseRecord,
    GhostWalkAuthorityEpochProvider,
    GhostWalkBindingPort,
    GhostWalkLeasePolicy,
    GhostWalkLeasePolicyRegistry,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkCapabilityBindingError,
    GhostWalkExecutableBinding,
)
from phios.spine.effects import EffectBoundaryContractError, normalize_effects
from phios.spine.ledger import RealityLedger
from phios.spine.models import ExecutionReceipt, GhostWalkExecutionProvenance
from phios.spine.runtime import PhiOSSpine

GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_lease_execution_receipt.v0.35"
)
GHOSTWALK_EXECUTION_PROVENANCE_SCHEMA_VERSION = (
    "phios.ghostwalk_execution_provenance.v0.35"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkLeaseExecutionError(ValueError):
    """Raised when lease-only execution inputs or custody cannot be trusted."""


def _require_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkLeaseExecutionError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkLeaseExecutionError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkLeaseExecutionError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkLeaseExecutionError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _optional_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field, maximum=maximum)


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
        raise GhostWalkLeaseExecutionError(
            "Ghost-Walk execution payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _parse_time(value: object, field: str) -> datetime:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkLeaseExecutionError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GhostWalkLeaseExecutionError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC)


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GhostWalkLeaseExecutionError(
            "execution clock must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GhostWalkLeaseExecutionReceipt:
    """Immutable custody/outcome record for one lease-only execution call."""

    status: str
    reason: str
    action_lease_sha256: str
    attempted_at: str
    lease_record_sha256: str | None
    target_inference_receipt_sha256: str | None
    executable_binding_sha256: str | None
    authority_epoch_sha256: str | None
    policy_sha256: str | None
    enforcement_profile_sha256: str | None
    spine_receipt_id: str | None
    spine_permission_status: str | None
    spine_execution_status: str | None
    executor_entered: bool
    lease_claimed: bool
    lease_consumed: bool
    replay_blocked: bool
    effect_performed: bool | None
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkLeaseExecutionError(
                "unsupported Ghost-Walk lease execution receipt schema"
            )
        if self.status not in {
            "HELD",
            "DENIED",
            "SUCCEEDED",
            "FAILED",
            "OUTCOME_UNKNOWN",
        }:
            raise GhostWalkLeaseExecutionError(
                "unsupported Ghost-Walk lease execution status"
            )
        _require_text(self.reason, "reason", maximum=512)
        _require_sha256(self.action_lease_sha256, "action_lease_sha256")
        canonical = _parse_time(self.attempted_at, "attempted_at")
        if canonical.isoformat() != self.attempted_at:
            raise GhostWalkLeaseExecutionError(
                "attempted_at must use canonical UTC ISO-8601 form"
            )
        for field, digest in (
            ("lease_record_sha256", self.lease_record_sha256),
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            ("executable_binding_sha256", self.executable_binding_sha256),
            ("authority_epoch_sha256", self.authority_epoch_sha256),
            ("policy_sha256", self.policy_sha256),
            (
                "enforcement_profile_sha256",
                self.enforcement_profile_sha256,
            ),
        ):
            _optional_sha256(digest, field)
        _optional_text(self.spine_receipt_id, "spine_receipt_id")
        _optional_text(
            self.spine_permission_status,
            "spine_permission_status",
            maximum=64,
        )
        _optional_text(
            self.spine_execution_status,
            "spine_execution_status",
            maximum=64,
        )
        for field, value in (
            ("executor_entered", self.executor_entered),
            ("lease_claimed", self.lease_claimed),
            ("lease_consumed", self.lease_consumed),
            ("replay_blocked", self.replay_blocked),
            ("action_authority", self.action_authority),
            ("execution_authority", self.execution_authority),
        ):
            if not isinstance(value, bool):
                raise GhostWalkLeaseExecutionError(
                    f"{field} must be Boolean"
                )
        if self.effect_performed not in {True, False, None}:
            raise GhostWalkLeaseExecutionError(
                "effect_performed must be Boolean or null"
            )
        if self.action_authority or self.execution_authority:
            raise GhostWalkLeaseExecutionError(
                "execution receipt cannot grant authority"
            )
        if self.lease_consumed and not self.lease_claimed:
            raise GhostWalkLeaseExecutionError(
                "consumed lease must have been claimed"
            )
        if self.executor_entered and not self.lease_claimed:
            raise GhostWalkLeaseExecutionError(
                "entered executor must have a claimed lease"
            )
        if self.status in {"HELD", "DENIED"}:
            if self.executor_entered or self.lease_consumed:
                raise GhostWalkLeaseExecutionError(
                    "held or denied execution cannot consume the lease"
                )
            if self.effect_performed is not False:
                raise GhostWalkLeaseExecutionError(
                    "held or denied execution cannot claim an effect"
                )
        if self.status == "SUCCEEDED":
            if (
                not self.executor_entered
                or not self.lease_consumed
                or self.effect_performed is not True
            ):
                raise GhostWalkLeaseExecutionError(
                    "successful execution receipt is incomplete"
                )
        if self.status in {"FAILED", "OUTCOME_UNKNOWN"}:
            if not self.executor_entered or not self.lease_consumed:
                raise GhostWalkLeaseExecutionError(
                    "entered failed/unknown execution must consume lease"
                )
            if self.effect_performed is not None:
                raise GhostWalkLeaseExecutionError(
                    "failed/unknown effect state must remain unknown"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "action_lease_sha256": self.action_lease_sha256,
            "attempted_at": self.attempted_at,
            "lease_record_sha256": self.lease_record_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "executable_binding_sha256": self.executable_binding_sha256,
            "authority_epoch_sha256": self.authority_epoch_sha256,
            "policy_sha256": self.policy_sha256,
            "enforcement_profile_sha256": (
                self.enforcement_profile_sha256
            ),
            "spine_receipt_id": self.spine_receipt_id,
            "spine_permission_status": self.spine_permission_status,
            "spine_execution_status": self.spine_execution_status,
            "executor_entered": self.executor_entered,
            "lease_claimed": self.lease_claimed,
            "lease_consumed": self.lease_consumed,
            "replay_blocked": self.replay_blocked,
            "effect_performed": self.effect_performed,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, object],
    ) -> "GhostWalkLeaseExecutionReceipt":
        expected = {
            "schema_version",
            "status",
            "reason",
            "action_lease_sha256",
            "attempted_at",
            "lease_record_sha256",
            "target_inference_receipt_sha256",
            "executable_binding_sha256",
            "authority_epoch_sha256",
            "policy_sha256",
            "enforcement_profile_sha256",
            "spine_receipt_id",
            "spine_permission_status",
            "spine_execution_status",
            "executor_entered",
            "lease_claimed",
            "lease_consumed",
            "replay_blocked",
            "effect_performed",
            "action_authority",
            "execution_authority",
            "receipt_sha256",
        }
        if set(value) != expected:
            raise GhostWalkLeaseExecutionError(
                "lease execution receipt fields do not match contract"
            )
        bool_fields = (
            "executor_entered",
            "lease_claimed",
            "lease_consumed",
            "replay_blocked",
            "action_authority",
            "execution_authority",
        )
        for field in bool_fields:
            if not isinstance(value.get(field), bool):
                raise GhostWalkLeaseExecutionError(
                    f"{field} must be Boolean"
                )
        effect = value.get("effect_performed")
        if effect not in {True, False, None}:
            raise GhostWalkLeaseExecutionError(
                "effect_performed must be Boolean or null"
            )
        item = cls(
            schema_version=_require_text(
                value.get("schema_version"),
                "schema_version",
                maximum=128,
            ),
            status=_require_text(
                value.get("status"),
                "status",
                maximum=64,
            ),
            reason=_require_text(value.get("reason"), "reason"),
            action_lease_sha256=_require_sha256(
                value.get("action_lease_sha256"),
                "action_lease_sha256",
            ),
            attempted_at=_require_text(
                value.get("attempted_at"),
                "attempted_at",
                maximum=64,
            ),
            lease_record_sha256=_optional_sha256(
                value.get("lease_record_sha256"),
                "lease_record_sha256",
            ),
            target_inference_receipt_sha256=_optional_sha256(
                value.get("target_inference_receipt_sha256"),
                "target_inference_receipt_sha256",
            ),
            executable_binding_sha256=_optional_sha256(
                value.get("executable_binding_sha256"),
                "executable_binding_sha256",
            ),
            authority_epoch_sha256=_optional_sha256(
                value.get("authority_epoch_sha256"),
                "authority_epoch_sha256",
            ),
            policy_sha256=_optional_sha256(
                value.get("policy_sha256"),
                "policy_sha256",
            ),
            enforcement_profile_sha256=_optional_sha256(
                value.get("enforcement_profile_sha256"),
                "enforcement_profile_sha256",
            ),
            spine_receipt_id=_optional_text(
                value.get("spine_receipt_id"),
                "spine_receipt_id",
            ),
            spine_permission_status=_optional_text(
                value.get("spine_permission_status"),
                "spine_permission_status",
                maximum=64,
            ),
            spine_execution_status=_optional_text(
                value.get("spine_execution_status"),
                "spine_execution_status",
                maximum=64,
            ),
            executor_entered=value["executor_entered"],
            lease_claimed=value["lease_claimed"],
            lease_consumed=value["lease_consumed"],
            replay_blocked=value["replay_blocked"],
            effect_performed=effect,
            action_authority=value["action_authority"],
            execution_authority=value["execution_authority"],
        )
        if value.get("receipt_sha256") != item.receipt_sha256:
            raise GhostWalkLeaseExecutionError(
                "lease execution receipt hash mismatch"
            )
        return item


class GhostWalkLeaseExecutionHandoff:
    """Execute exactly one lease-owned Ghost-Walk binding.

    Public execution is intentionally lease-only:

        execute(action_lease_sha256=...)

    Every executable detail is recovered server-side.
    """

    def __init__(
        self,
        *,
        ledger: RealityLedger,
        capability_bindings: GhostWalkBindingPort,
        policies: GhostWalkLeasePolicyRegistry,
        authority_epochs: GhostWalkAuthorityEpochProvider,
        spine: PhiOSSpine,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkLeaseExecutionError(
                "ledger must be a RealityLedger"
            )
        if spine.ledger.path != ledger.path:
            raise GhostWalkLeaseExecutionError(
                "execution Spine and Ghost-Walk custody must share one RealityLedger"
            )
        self._ledger = ledger
        self._capability_bindings = capability_bindings
        self._policies = policies
        self._authority_epochs = authority_epochs
        self._spine = spine
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    def execute(
        self,
        *,
        action_lease_sha256: str,
    ) -> GhostWalkLeaseExecutionReceipt:
        lease_sha = _require_sha256(
            action_lease_sha256,
            "action_lease_sha256",
        )
        attempted_at = _canonical_time(self._now())

        with self._lock:
            record = self._lease_record(lease_sha)
            if record is None:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="lease_not_found",
                )

            binding = self._current_binding(record)
            if binding is None:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="executable_binding_stale",
                    record=record,
                )

            policy, profile = self._current_policy_and_profile(
                record=record,
                binding=binding,
            )
            if policy is None or profile is None:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="lease_policy_or_enforcement_changed",
                    record=record,
                    binding=binding,
                )

            epoch = self._current_epoch()
            if epoch is None:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="authority_epoch_unavailable",
                    record=record,
                    binding=binding,
                    policy=policy,
                    profile=profile,
                )
            if (
                epoch.authority_epoch_sha256
                != record.action_lease.authority_epoch_sha256
            ):
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="authority_epoch_changed",
                    record=record,
                    binding=binding,
                    policy=policy,
                    profile=profile,
                    authority_epoch_sha256=(
                        epoch.authority_epoch_sha256
                    ),
                )

            self._validate_exact_scope(
                record=record,
                binding=binding,
                policy=policy,
                profile=profile,
            )
            scope_reason = self._runtime_scope_reason(binding)
            if scope_reason is not None:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason=scope_reason,
                    record=record,
                    binding=binding,
                    policy=policy,
                    profile=profile,
                    authority_epoch_sha256=(
                        epoch.authority_epoch_sha256
                    ),
                )

            try:
                consumed = self._ledger.has_consumed_action_lease(
                    lease_sha
                )
                evaluation = evaluate_action_lease(
                    lease=record.action_lease,
                    checked_at=attempted_at,
                    current_authority_epoch_sha256=(
                        epoch.authority_epoch_sha256
                    ),
                    uses_consumed=1 if consumed else 0,
                )
            except (
                OSError,
                json.JSONDecodeError,
                ValueError,
                ActionLeaseContractError,
            ) as exc:
                raise GhostWalkLeaseExecutionError(
                    "ActionLease currency could not be verified safely"
                ) from exc

            if not evaluation.usable:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason=evaluation.reason,
                    record=record,
                    binding=binding,
                    policy=policy,
                    profile=profile,
                    authority_epoch_sha256=(
                        epoch.authority_epoch_sha256
                    ),
                    replay_blocked=(
                        evaluation.reason == "lease_consumed"
                    ),
                )

            try:
                claimed = self._ledger.claim_action_lease(lease_sha)
            except (OSError, ValueError) as exc:
                raise GhostWalkLeaseExecutionError(
                    "ActionLease could not be claimed safely"
                ) from exc
            if not claimed:
                return self._held(
                    lease_sha=lease_sha,
                    attempted_at=attempted_at,
                    reason="lease_execution_claim_unavailable",
                    record=record,
                    binding=binding,
                    policy=policy,
                    profile=profile,
                    authority_epoch_sha256=(
                        epoch.authority_epoch_sha256
                    ),
                    replay_blocked=True,
                )

            provenance = GhostWalkExecutionProvenance(
                schema_version=(
                    GHOSTWALK_EXECUTION_PROVENANCE_SCHEMA_VERSION
                ),
                target_inference_receipt_sha256=(
                    record.target_inference_receipt_sha256
                ),
                authorization_decision_sha256=(
                    binding.authorization_decision_sha256
                ),
                executable_binding_sha256=(
                    binding.executable_binding_sha256
                ),
                lease_record_sha256=record.lease_record_sha256,
                action_lease_sha256=lease_sha,
                authority_epoch_sha256=(
                    epoch.authority_epoch_sha256
                ),
                policy_sha256=policy.policy_sha256,
                enforcement_profile_sha256=profile.profile_sha256,
            )

            try:
                execution = self._spine.run(
                    binding.capability_id,
                    dict(binding.payload),
                    governed_provenance=provenance,
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._ledger.release_action_lease_claim(lease_sha)
                raise GhostWalkLeaseExecutionError(
                    "Spine rejected execution before a receipted executor attempt"
                ) from exc
            except Exception as exc:
                raise GhostWalkLeaseExecutionError(
                    "unexpected Spine failure after lease claim; claim retained fail-closed"
                ) from exc

            self._validate_spine_receipt(
                execution=execution,
                binding=binding,
                provenance=provenance,
            )
            return self._complete(
                lease_sha=lease_sha,
                attempted_at=attempted_at,
                record=record,
                binding=binding,
                policy=policy,
                profile=profile,
                authority_epoch_sha256=(
                    epoch.authority_epoch_sha256
                ),
                execution=execution,
            )

    def _lease_record(
        self,
        lease_sha: str,
    ) -> GhostWalkActionLeaseRecord | None:
        rows = self._ledger.ghostwalk_action_lease_records(
            action_lease_sha256=lease_sha
        )
        records: list[GhostWalkActionLeaseRecord] = []
        for row in rows:
            try:
                records.append(
                    GhostWalkActionLeaseRecord.from_dict(row)
                )
            except GhostWalkActionLeaseError as exc:
                raise GhostWalkLeaseExecutionError(
                    "persisted Ghost-Walk ActionLease custody is invalid"
                ) from exc
        if len(records) > 1:
            raise GhostWalkLeaseExecutionError(
                "ActionLease identity is not unique in Ghost-Walk custody"
            )
        if not records:
            return None
        record = records[0]
        if record.action_lease.action_lease_sha256 != lease_sha:
            raise GhostWalkLeaseExecutionError(
                "ActionLease lookup returned mismatched custody"
            )
        return record

    def _current_binding(
        self,
        record: GhostWalkActionLeaseRecord,
    ) -> GhostWalkExecutableBinding | None:
        try:
            binding = self._capability_bindings.latest(
                target_inference_receipt_sha256=(
                    record.target_inference_receipt_sha256
                )
            )
            readiness = self._capability_bindings.readiness(
                target_inference_receipt_sha256=(
                    record.target_inference_receipt_sha256
                )
            )
        except GhostWalkCapabilityBindingError as exc:
            raise GhostWalkLeaseExecutionError(
                "current executable binding could not be verified"
            ) from exc
        if binding is None:
            return None
        if (
            binding.executable_binding_sha256
            != record.executable_binding_sha256
        ):
            return None
        reason = getattr(readiness, "reason", None)
        existing = getattr(
            readiness,
            "existing_binding_sha256",
            None,
        )
        if (
            reason
            is not GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS
            or existing != binding.executable_binding_sha256
        ):
            return None
        return binding

    def _current_policy_and_profile(
        self,
        *,
        record: GhostWalkActionLeaseRecord,
        binding: GhostWalkExecutableBinding,
    ) -> tuple[
        GhostWalkLeasePolicy | None,
        EnforcementProfile | None,
    ]:
        policy = self._policies.for_binding(binding)
        if policy is None or policy.policy_sha256 != record.policy_sha256:
            return None, None
        try:
            profile = EnforcementProfile.build(
                intent=binding.effect_intent,
                rules=policy.enforcement_rules,
            )
        except EnforcementProfileContractError as exc:
            raise GhostWalkLeaseExecutionError(
                "current lease policy cannot reconstruct EnforcementProfile"
            ) from exc
        if (
            profile.profile_sha256
            != record.enforcement_profile.profile_sha256
        ):
            return None, None
        if (
            policy.accepted_unenforced_effects
            != profile.effects_without_enforced_rule
        ):
            return None, None
        return policy, profile

    def _current_epoch(self) -> AuthorityEpoch | None:
        try:
            return self._authority_epochs.current()
        except AuthorityEpochContractError as exc:
            raise GhostWalkLeaseExecutionError(
                "current AuthorityEpoch could not be verified"
            ) from exc

    def _validate_exact_scope(
        self,
        *,
        record: GhostWalkActionLeaseRecord,
        binding: GhostWalkExecutableBinding,
        policy: GhostWalkLeasePolicy,
        profile: EnforcementProfile,
    ) -> None:
        lease = record.action_lease
        mismatches = (
            lease.authorization_receipt_sha256
            != binding.authorization_decision_sha256,
            lease.effect_intent_sha256
            != binding.effect_intent.effect_intent_sha256,
            lease.enforcement_profile_sha256
            != profile.profile_sha256,
            lease.capability_id != binding.capability_id,
            lease.capability_version != binding.capability_version,
            lease.payload_sha256 != binding.payload_sha256,
            lease.effects_declared != binding.effects_declared,
            lease.permissions_authorized
            != binding.permissions_required,
            lease.principal_id != policy.principal_id,
            lease.issuer_id != policy.issuer_id,
            lease.accepted_unenforced_effects
            != policy.accepted_unenforced_effects,
        )
        if any(mismatches):
            raise GhostWalkLeaseExecutionError(
                "ActionLease scope diverges from current Ghost-Walk custody"
            )

    def _runtime_scope_reason(
        self,
        binding: GhostWalkExecutableBinding,
    ) -> str | None:
        try:
            capability = self._spine.registry.get(
                binding.capability_id
            )
        except KeyError:
            return "capability_not_registered"

        try:
            effects = normalize_effects(
                capability.effects,
                label="runtime capability effects",
            )
        except EffectBoundaryContractError:
            return "capability_effect_contract_invalid"

        if (
            capability.version != binding.capability_version
            or tuple(capability.permissions)
            != binding.permissions_required
            or effects != binding.effects_declared
        ):
            return "capability_contract_drift"

        try:
            executor_effects = self._spine.executors.effects(
                capability.id
            )
        except KeyError:
            return "executor_effect_contract_missing"
        decision = self._spine.effect_policy.evaluate(
            capability,
            executor_effects=executor_effects,
        )
        if not decision.allowed:
            return f"effect_boundary_{decision.reason}"
        return None

    @staticmethod
    def _validate_spine_receipt(
        *,
        execution: ExecutionReceipt,
        binding: GhostWalkExecutableBinding,
        provenance: GhostWalkExecutionProvenance,
    ) -> None:
        if execution.capability_id != binding.capability_id:
            raise GhostWalkLeaseExecutionError(
                "Spine receipt capability diverged from binding"
            )
        if execution.input_sha256 != binding.payload_sha256:
            raise GhostWalkLeaseExecutionError(
                "Spine receipt payload diverged from binding"
            )
        if execution.permissions_requested != list(
            binding.permissions_required
        ):
            raise GhostWalkLeaseExecutionError(
                "Spine permission request diverged from binding"
            )
        if execution.governed_provenance != provenance:
            raise GhostWalkLeaseExecutionError(
                "Spine execution provenance diverged from Ghost-Walk custody"
            )

    def _complete(
        self,
        *,
        lease_sha: str,
        attempted_at: str,
        record: GhostWalkActionLeaseRecord,
        binding: GhostWalkExecutableBinding,
        policy: GhostWalkLeasePolicy,
        profile: EnforcementProfile,
        authority_epoch_sha256: str,
        execution: ExecutionReceipt,
    ) -> GhostWalkLeaseExecutionReceipt:
        if execution.permission_status == "denied":
            self._ledger.release_action_lease_claim(lease_sha)
            return self._record_receipt(
                status="DENIED",
                reason=execution.error or "spine_permission_denied",
                lease_sha=lease_sha,
                attempted_at=attempted_at,
                record=record,
                binding=binding,
                policy=policy,
                profile=profile,
                authority_epoch_sha256=authority_epoch_sha256,
                spine_receipt_id=execution.receipt_id,
                spine_permission_status=execution.permission_status,
                spine_execution_status=execution.execution_status,
                executor_entered=False,
                lease_claimed=True,
                lease_consumed=False,
                replay_blocked=False,
                effect_performed=False,
            )

        if execution.permission_status != "allowed":
            if not execution.executor_entered:
                self._ledger.release_action_lease_claim(lease_sha)
            raise GhostWalkLeaseExecutionError(
                "Spine returned unsupported permission state"
            )

        outcomes: dict[str, tuple[str, str, bool | None]] = {
            "succeeded": (
                "SUCCEEDED",
                "spine_execution_succeeded",
                True,
            ),
            "failed": (
                "FAILED",
                "spine_execution_failed",
                None,
            ),
            "outcome_unknown": (
                "OUTCOME_UNKNOWN",
                "spine_execution_outcome_unknown",
                None,
            ),
        }
        selected = outcomes.get(execution.execution_status)
        if selected is None:
            if not execution.executor_entered:
                self._ledger.release_action_lease_claim(lease_sha)
            raise GhostWalkLeaseExecutionError(
                "Spine returned unsupported execution state"
            )
        status, reason, effect_performed = selected
        if not execution.executor_entered:
            self._ledger.release_action_lease_claim(lease_sha)
            raise GhostWalkLeaseExecutionError(
                "effectful Spine outcome did not record executor entry"
            )

        return self._record_receipt(
            status=status,
            reason=reason,
            lease_sha=lease_sha,
            attempted_at=attempted_at,
            record=record,
            binding=binding,
            policy=policy,
            profile=profile,
            authority_epoch_sha256=authority_epoch_sha256,
            spine_receipt_id=execution.receipt_id,
            spine_permission_status=execution.permission_status,
            spine_execution_status=execution.execution_status,
            executor_entered=True,
            lease_claimed=True,
            lease_consumed=True,
            replay_blocked=False,
            effect_performed=effect_performed,
        )
