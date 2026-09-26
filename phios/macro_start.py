"""Zero-authority trigger observation and governed macro-run start admission.

v0.8 defines how an external observation may request creation of one already
planned macro run. Admission is not execution authority. The resulting run
still pauses at the same v0.4/v0.5 authority boundaries.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from phios.macro_coordinator import (
    CoordinatedRun,
    MacroRunCoordinator,
    MacroRunCoordinatorContractError,
)
from phios.macro_graph import MacroPlan
from phios.spine.ledger import RealityLedger

TRIGGER_OBSERVATION_SCHEMA_VERSION = "phios.trigger_observation.v0.8"
RUN_START_REQUEST_SCHEMA_VERSION = "phios.run_start_request.v0.8"
RUN_START_POLICY_SCHEMA_VERSION = "phios.run_start_admission_policy.v0.8"
RUN_START_RECEIPT_SCHEMA_VERSION = "phios.run_start_receipt.v0.8"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroRunStartContractError(ValueError):
    """Raised when trigger/start scope cannot be represented safely."""


class StartStatus(StrEnum):
    STARTED = "STARTED"
    HELD = "HELD"
    REJECTED = "REJECTED"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroRunStartContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise MacroRunStartContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise MacroRunStartContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroRunStartContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MacroRunStartContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MacroRunStartContractError(
            f"{field} must include a timezone"
        )
    return text


def _canonical_names(
    values: tuple[str, ...],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise MacroRunStartContractError(
            f"{field} must not be empty"
        )
    normalized = tuple(
        _require_text(value, f"{field} item")
        for value in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise MacroRunStartContractError(
            f"{field} must be sorted and unique"
        )
    return normalized


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
        raise MacroRunStartContractError(
            "run-start payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TriggerObservation:
    """One external observation with no authority over a macro run."""

    observation_id: str
    trigger_type: str
    source_id: str
    source_event_id: str
    observed_at: str
    payload_sha256: str
    evidence_ref_sha256s: tuple[str, ...] = ()
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRIGGER_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRIGGER_OBSERVATION_SCHEMA_VERSION:
            raise MacroRunStartContractError(
                "unsupported trigger observation schema"
            )
        _require_text(self.observation_id, "observation_id")
        _require_text(self.trigger_type, "trigger_type")
        _require_text(self.source_id, "source_id")
        _require_text(self.source_event_id, "source_event_id")
        _require_timestamp(self.observed_at, "observed_at")
        _require_sha256(self.payload_sha256, "payload_sha256")
        for evidence in self.evidence_ref_sha256s:
            _require_sha256(evidence, "evidence_ref_sha256")
        if tuple(sorted(set(self.evidence_ref_sha256s))) != (
            self.evidence_ref_sha256s
        ):
            raise MacroRunStartContractError(
                "evidence_ref_sha256s must be sorted and unique"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunStartContractError(
                "TriggerObservation cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "trigger_type": self.trigger_type,
            "source_id": self.source_id,
            "source_event_id": self.source_event_id,
            "observed_at": self.observed_at,
            "payload_sha256": self.payload_sha256,
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["observation_sha256"] = self.observation_sha256
        return payload


@dataclass(frozen=True, slots=True)
class RunStartRequest:
    """Zero-authority request to start one exact MacroPlan under one run_id."""

    request_id: str
    run_id: str
    macro_id: str
    macro_version: str
    plan_sha256: str
    trigger_observation_sha256: str
    trigger_type: str
    source_id: str
    source_event_id: str
    dedupe_sha256: str
    requested_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = RUN_START_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUN_START_REQUEST_SCHEMA_VERSION:
            raise MacroRunStartContractError(
                "unsupported run start request schema"
            )
        _require_text(self.request_id, "request_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        _require_sha256(
            self.trigger_observation_sha256,
            "trigger_observation_sha256",
        )
        _require_text(self.trigger_type, "trigger_type")
        _require_text(self.source_id, "source_id")
        _require_text(self.source_event_id, "source_event_id")
        _require_sha256(self.dedupe_sha256, "dedupe_sha256")
        _require_timestamp(self.requested_at, "requested_at")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunStartContractError(
                "RunStartRequest cannot carry authority"
            )

    @classmethod
    def build(
        cls,
        *,
        request_id: str,
        run_id: str,
        plan: MacroPlan,
        observation: TriggerObservation,
        requested_at: str,
    ) -> "RunStartRequest":
        dedupe_sha256 = _canonical_sha256(
            {
                "trigger_observation_sha256": (
                    observation.observation_sha256
                ),
                "macro_id": plan.macro_id,
                "macro_version": plan.macro_version,
                "plan_sha256": plan.plan_sha256,
            }
        )
        return cls(
            request_id=request_id,
            run_id=run_id,
            macro_id=plan.macro_id,
            macro_version=plan.macro_version,
            plan_sha256=plan.plan_sha256,
            trigger_observation_sha256=observation.observation_sha256,
            trigger_type=observation.trigger_type,
            source_id=observation.source_id,
            source_event_id=observation.source_event_id,
            dedupe_sha256=dedupe_sha256,
            requested_at=requested_at,
        )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "trigger_observation_sha256": (
                self.trigger_observation_sha256
            ),
            "trigger_type": self.trigger_type,
            "source_id": self.source_id,
            "source_event_id": self.source_event_id,
            "dedupe_sha256": self.dedupe_sha256,
            "requested_at": self.requested_at,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def request_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    @property
    def run_id_sha256(self) -> str:
        return _canonical_sha256({"run_id": self.run_id})

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["request_sha256"] = self.request_sha256
        payload["run_id_sha256"] = self.run_id_sha256
        return payload


@dataclass(frozen=True, slots=True)
class RunStartAdmissionPolicy:
    """Non-authority allowlist for admitting start requests into coordination."""

    policy_id: str
    allowed_trigger_types: tuple[str, ...]
    allowed_source_ids: tuple[str, ...]
    enabled: bool = True
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = RUN_START_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUN_START_POLICY_SCHEMA_VERSION:
            raise MacroRunStartContractError(
                "unsupported run start admission policy schema"
            )
        _require_text(self.policy_id, "policy_id")
        _canonical_names(
            self.allowed_trigger_types,
            "allowed_trigger_types",
            allow_empty=False,
        )
        _canonical_names(
            self.allowed_source_ids,
            "allowed_source_ids",
            allow_empty=False,
        )
        if not isinstance(self.enabled, bool):
            raise MacroRunStartContractError("enabled must be Boolean")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunStartContractError(
                "RunStartAdmissionPolicy cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "allowed_trigger_types": list(self.allowed_trigger_types),
            "allowed_source_ids": list(self.allowed_source_ids),
            "enabled": self.enabled,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def policy_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["policy_sha256"] = self.policy_sha256
        return payload


@dataclass(frozen=True, slots=True)
class RunStartReceipt:
    """Append-only evidence for one STARTED / HELD / REJECTED request."""

    status: StartStatus
    reason: str
    request_id: str
    request_sha256: str
    run_id: str
    run_id_sha256: str
    macro_id: str
    macro_version: str
    plan_sha256: str
    trigger_observation_sha256: str
    trigger_type: str
    source_id: str
    source_event_id: str
    dedupe_sha256: str
    policy_id: str
    policy_sha256: str
    journal_head_sha256: str | None
    run_state_sha256: str | None
    run_status: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = RUN_START_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUN_START_RECEIPT_SCHEMA_VERSION:
            raise MacroRunStartContractError(
                "unsupported run start receipt schema"
            )
        _require_text(self.reason, "reason")
        _require_text(self.request_id, "request_id")
        _require_sha256(self.request_sha256, "request_sha256")
        _require_text(self.run_id, "run_id")
        _require_sha256(self.run_id_sha256, "run_id_sha256")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        _require_sha256(
            self.trigger_observation_sha256,
            "trigger_observation_sha256",
        )
        _require_text(self.trigger_type, "trigger_type")
        _require_text(self.source_id, "source_id")
        _require_text(self.source_event_id, "source_event_id")
        _require_sha256(self.dedupe_sha256, "dedupe_sha256")
        _require_text(self.policy_id, "policy_id")
        _require_sha256(self.policy_sha256, "policy_sha256")
        if self.journal_head_sha256 is not None:
            _require_sha256(
                self.journal_head_sha256,
                "journal_head_sha256",
            )
        if self.run_state_sha256 is not None:
            _require_sha256(
                self.run_state_sha256,
                "run_state_sha256",
            )
        if self.run_status is not None:
            _require_text(self.run_status, "run_status", maximum=64)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunStartContractError(
                "RunStartReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "reason": self.reason,
            "request_id": self.request_id,
            "request_sha256": self.request_sha256,
            "run_id": self.run_id,
            "run_id_sha256": self.run_id_sha256,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "trigger_observation_sha256": (
                self.trigger_observation_sha256
            ),
            "trigger_type": self.trigger_type,
            "source_id": self.source_id,
            "source_event_id": self.source_event_id,
            "dedupe_sha256": self.dedupe_sha256,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "journal_head_sha256": self.journal_head_sha256,
            "run_state_sha256": self.run_state_sha256,
            "run_status": self.run_status,
            "operational_authority": self.operational_authority,
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


@dataclass(frozen=True, slots=True)
class RunStartAdmission:
    receipt: RunStartReceipt
    run: CoordinatedRun | None


class MacroRunStartGate:
    """Admit one zero-authority start request into MacroRunCoordinator."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise MacroRunStartContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger
        self._coordinator = MacroRunCoordinator(ledger)

    def admit(
        self,
        *,
        observation: TriggerObservation,
        request: RunStartRequest,
        policy: RunStartAdmissionPolicy,
        plan: MacroPlan,
    ) -> RunStartAdmission:
        scope_reason = self._scope_reason(
            observation=observation,
            request=request,
            plan=plan,
        )
        if scope_reason is not None:
            return self._record(
                status=StartStatus.REJECTED,
                reason=scope_reason,
                request=request,
                policy=policy,
                run=None,
            )

        if not policy.enabled:
            return self._record(
                status=StartStatus.HELD,
                reason="start_policy_disabled",
                request=request,
                policy=policy,
                run=None,
            )
        if request.trigger_type not in policy.allowed_trigger_types:
            return self._record(
                status=StartStatus.REJECTED,
                reason="trigger_type_not_allowed",
                request=request,
                policy=policy,
                run=None,
            )
        if request.source_id not in policy.allowed_source_ids:
            return self._record(
                status=StartStatus.REJECTED,
                reason="trigger_source_not_allowed",
                request=request,
                policy=policy,
                run=None,
            )

        if self._coordinator.has_run(run_id=request.run_id):
            return self._record(
                status=StartStatus.HELD,
                reason="run_id_exists",
                request=request,
                policy=policy,
                run=None,
            )

        if not self._ledger.claim_macro_start_dedupe(
            request.dedupe_sha256
        ):
            return self._record(
                status=StartStatus.HELD,
                reason="trigger_already_admitted",
                request=request,
                policy=policy,
                run=None,
            )

        if not self._ledger.claim_macro_run_id(request.run_id_sha256):
            self._ledger.release_macro_start_dedupe_claim(
                request.dedupe_sha256
            )
            return self._record(
                status=StartStatus.HELD,
                reason="run_id_claimed",
                request=request,
                policy=policy,
                run=None,
            )

        try:
            run = self._coordinator.start_run(
                run_id=request.run_id,
                plan=plan,
            )
        except MacroRunCoordinatorContractError:
            self._ledger.release_macro_run_id_claim(
                request.run_id_sha256
            )
            self._ledger.release_macro_start_dedupe_claim(
                request.dedupe_sha256
            )
            if self._coordinator.has_run(run_id=request.run_id):
                return self._record(
                    status=StartStatus.HELD,
                    reason="run_id_exists",
                    request=request,
                    policy=policy,
                    run=None,
                )
            raise

        return self._record(
            status=StartStatus.STARTED,
            reason="start_request_admitted",
            request=request,
            policy=policy,
            run=run,
        )

    @staticmethod
    def _scope_reason(
        *,
        observation: TriggerObservation,
        request: RunStartRequest,
        plan: MacroPlan,
    ) -> str | None:
        if request.trigger_observation_sha256 != (
            observation.observation_sha256
        ):
            return "trigger_observation_hash_mismatch"
        if request.trigger_type != observation.trigger_type:
            return "trigger_type_scope_mismatch"
        if request.source_id != observation.source_id:
            return "trigger_source_scope_mismatch"
        if request.source_event_id != observation.source_event_id:
            return "trigger_event_scope_mismatch"
        if (
            request.macro_id != plan.macro_id
            or request.macro_version != plan.macro_version
            or request.plan_sha256 != plan.plan_sha256
        ):
            return "macro_plan_scope_mismatch"

        expected_dedupe = _canonical_sha256(
            {
                "trigger_observation_sha256": (
                    observation.observation_sha256
                ),
                "macro_id": plan.macro_id,
                "macro_version": plan.macro_version,
                "plan_sha256": plan.plan_sha256,
            }
        )
        if request.dedupe_sha256 != expected_dedupe:
            return "dedupe_scope_mismatch"
        return None

    def _record(
        self,
        *,
        status: StartStatus,
        reason: str,
        request: RunStartRequest,
        policy: RunStartAdmissionPolicy,
        run: CoordinatedRun | None,
    ) -> RunStartAdmission:
        receipt = RunStartReceipt(
            status=status,
            reason=reason,
            request_id=request.request_id,
            request_sha256=request.request_sha256,
            run_id=request.run_id,
            run_id_sha256=request.run_id_sha256,
            macro_id=request.macro_id,
            macro_version=request.macro_version,
            plan_sha256=request.plan_sha256,
            trigger_observation_sha256=(
                request.trigger_observation_sha256
            ),
            trigger_type=request.trigger_type,
            source_id=request.source_id,
            source_event_id=request.source_event_id,
            dedupe_sha256=request.dedupe_sha256,
            policy_id=policy.policy_id,
            policy_sha256=policy.policy_sha256,
            journal_head_sha256=(
                run.head_entry_sha256 if run is not None else None
            ),
            run_state_sha256=(
                run.state.state_sha256 if run is not None else None
            ),
            run_status=(
                run.state.status.value if run is not None else None
            ),
        )
        self._ledger.append_macro_run_start_receipt(receipt)
        return RunStartAdmission(receipt=receipt, run=run)
