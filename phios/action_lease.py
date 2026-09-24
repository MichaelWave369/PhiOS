"""Canonical bounded action-authority lease for PhiOS.

ActionLease binds one explicit authorization decision to one principal, one
EffectIntent, one EnforcementProfile, and one AuthorityEpoch for a bounded
time and use count. It carries narrow action authority, never execution
authority, and performs no effect by itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from phios.authority_epoch import AuthorityEpoch
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile
from phios.spine.effects import EffectBoundaryContractError, normalize_effects

ACTION_LEASE_SCHEMA_VERSION = "phios.action_lease.v0.1"
ACTION_LEASE_EVALUATION_SCHEMA_VERSION = "phios.action_lease_evaluation.v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ActionLeaseContractError(ValueError):
    """Raised when an ActionLease violates the canonical contract."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise ActionLeaseContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise ActionLeaseContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise ActionLeaseContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ActionLeaseContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _parse_time(value: object, field: str) -> datetime:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ActionLeaseContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ActionLeaseContractError(
            f"{field} must include a timezone offset"
        )
    return parsed.astimezone(UTC)


def _canonical_time(value: object, field: str) -> str:
    return _parse_time(value, field).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ActionLeaseContractError(
            "ActionLease payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _canonical_text_tuple(
    values: tuple[str, ...],
    field: str,
) -> tuple[str, ...]:
    normalized = tuple(
        _require_text(item, f"{field} item")
        for item in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise ActionLeaseContractError(
            f"{field} must be sorted and unique"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ActionLease:
    """One bounded authorization for one exact action intent.

    The lease carries action authority only. Execution still requires a later
    runtime handoff that verifies current authority state, lease status,
    consumption state, capability contract, and executor boundary.
    """

    principal_id: str
    issuer_id: str
    authorization_receipt_sha256: str
    effect_intent_sha256: str
    enforcement_profile_sha256: str
    authority_epoch_sha256: str
    capability_id: str
    capability_version: str
    payload_sha256: str
    effects_declared: tuple[str, ...]
    permissions_authorized: tuple[str, ...]
    accepted_unenforced_effects: tuple[str, ...]
    issued_at: str
    valid_from: str
    valid_until: str
    max_uses: int = 1
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = True
    execution_authority: bool = False
    schema_version: str = ACTION_LEASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTION_LEASE_SCHEMA_VERSION:
            raise ActionLeaseContractError(
                f"unsupported ActionLease schema: {self.schema_version}"
            )
        _require_text(self.principal_id, "principal_id")
        _require_text(self.issuer_id, "issuer_id")
        for field, digest in (
            (
                "authorization_receipt_sha256",
                self.authorization_receipt_sha256,
            ),
            ("effect_intent_sha256", self.effect_intent_sha256),
            (
                "enforcement_profile_sha256",
                self.enforcement_profile_sha256,
            ),
            ("authority_epoch_sha256", self.authority_epoch_sha256),
            ("payload_sha256", self.payload_sha256),
        ):
            _require_sha256(digest, field)

        _require_text(self.capability_id, "capability_id")
        _require_text(
            self.capability_version,
            "capability_version",
            maximum=128,
        )
        _canonical_text_tuple(
            self.effects_declared,
            "effects_declared",
        )
        try:
            normalized_effects = normalize_effects(
                self.effects_declared,
                label="lease effects_declared",
            )
        except EffectBoundaryContractError as exc:
            raise ActionLeaseContractError(str(exc)) from exc
        if normalized_effects != self.effects_declared:
            raise ActionLeaseContractError(
                "effects_declared must be canonical PhiOS effects"
            )
        if "unknown" in self.effects_declared:
            raise ActionLeaseContractError(
                "ActionLease cannot authorize unknown effects"
            )
        if self.effects_declared == ("none",):
            raise ActionLeaseContractError(
                "ActionLease cannot authorize a none EffectIntent"
            )

        _canonical_text_tuple(
            self.permissions_authorized,
            "permissions_authorized",
        )
        if not self.permissions_authorized:
            raise ActionLeaseContractError(
                "permissions_authorized must not be empty"
            )
        _canonical_text_tuple(
            self.accepted_unenforced_effects,
            "accepted_unenforced_effects",
        )
        if not set(self.accepted_unenforced_effects).issubset(
            set(self.effects_declared)
        ):
            raise ActionLeaseContractError(
                "accepted_unenforced_effects must be a subset of effects_declared"
            )

        issued = _parse_time(self.issued_at, "issued_at")
        valid_from = _parse_time(self.valid_from, "valid_from")
        valid_until = _parse_time(self.valid_until, "valid_until")
        if self.issued_at != issued.isoformat():
            raise ActionLeaseContractError(
                "issued_at must use canonical UTC ISO-8601 form"
            )
        if self.valid_from != valid_from.isoformat():
            raise ActionLeaseContractError(
                "valid_from must use canonical UTC ISO-8601 form"
            )
        if self.valid_until != valid_until.isoformat():
            raise ActionLeaseContractError(
                "valid_until must use canonical UTC ISO-8601 form"
            )
        if valid_from < issued:
            raise ActionLeaseContractError(
                "valid_from cannot be earlier than issued_at"
            )
        if valid_until <= valid_from:
            raise ActionLeaseContractError(
                "valid_until must be later than valid_from"
            )

        if isinstance(self.max_uses, bool) or not isinstance(
            self.max_uses,
            int,
        ):
            raise ActionLeaseContractError(
                "max_uses must be an integer"
            )
        if self.max_uses != 1:
            raise ActionLeaseContractError(
                "ActionLease v0.1 is single-use and requires max_uses = 1"
            )

        if self.effect_performed is not False:
            raise ActionLeaseContractError(
                "ActionLease cannot claim an effect was performed"
            )
        if self.operational_authority is not False:
            raise ActionLeaseContractError(
                "ActionLease cannot carry broad operational authority"
            )
        if self.action_authority is not True:
            raise ActionLeaseContractError(
                "ActionLease must carry its bounded action authority"
            )
        if self.execution_authority is not False:
            raise ActionLeaseContractError(
                "ActionLease cannot carry execution authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "principal_id": self.principal_id,
            "issuer_id": self.issuer_id,
            "authorization_receipt_sha256": (
                self.authorization_receipt_sha256
            ),
            "effect_intent_sha256": self.effect_intent_sha256,
            "enforcement_profile_sha256": (
                self.enforcement_profile_sha256
            ),
            "authority_epoch_sha256": self.authority_epoch_sha256,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "payload_sha256": self.payload_sha256,
            "effects_declared": list(self.effects_declared),
            "permissions_authorized": list(
                self.permissions_authorized
            ),
            "accepted_unenforced_effects": list(
                self.accepted_unenforced_effects
            ),
            "issued_at": self.issued_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "max_uses": self.max_uses,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def action_lease_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["action_lease_sha256"] = self.action_lease_sha256
        return payload

    @classmethod
    def issue(
        cls,
        *,
        principal_id: str,
        issuer_id: str,
        authorization_receipt_sha256: str,
        intent: EffectIntent,
        enforcement: EnforcementProfile,
        authority_epoch: AuthorityEpoch,
        permissions_authorized: tuple[str, ...],
        accepted_unenforced_effects: tuple[str, ...],
        issued_at: str,
        valid_from: str,
        valid_until: str,
    ) -> "ActionLease":
        principal = _require_text(principal_id, "principal_id")
        if principal != authority_epoch.principal_id:
            raise ActionLeaseContractError(
                "lease principal does not match AuthorityEpoch principal"
            )
        issuer = _require_text(issuer_id, "issuer_id")
        authorization_receipt = _require_sha256(
            authorization_receipt_sha256,
            "authorization_receipt_sha256",
        )

        if intent.effects_declared == ("none",):
            raise ActionLeaseContractError(
                "ActionLease cannot authorize a none EffectIntent"
            )
        if (
            enforcement.effect_intent_sha256
            != intent.effect_intent_sha256
        ):
            raise ActionLeaseContractError(
                "EnforcementProfile does not bind the supplied EffectIntent"
            )
        if not enforcement.mapping_complete:
            raise ActionLeaseContractError(
                "cannot issue ActionLease with unmapped effects"
            )

        expected_unenforced = tuple(
            sorted(enforcement.effects_without_enforced_rule)
        )
        accepted_unenforced = tuple(
            sorted(set(accepted_unenforced_effects))
        )
        if accepted_unenforced != expected_unenforced:
            raise ActionLeaseContractError(
                "accepted_unenforced_effects must exactly acknowledge "
                "effects without an enforced rule"
            )

        permissions = tuple(sorted(set(permissions_authorized)))
        if not permissions:
            raise ActionLeaseContractError(
                "permissions_authorized must not be empty"
            )
        if not set(permissions).issubset(set(authority_epoch.grants)):
            raise ActionLeaseContractError(
                "lease permissions exceed AuthorityEpoch grants"
            )

        issued = _canonical_time(issued_at, "issued_at")
        starts = _canonical_time(valid_from, "valid_from")
        ends = _canonical_time(valid_until, "valid_until")
        epoch_observed = _parse_time(
            authority_epoch.observed_at,
            "AuthorityEpoch observed_at",
        )
        if _parse_time(issued, "issued_at") < epoch_observed:
            raise ActionLeaseContractError(
                "lease cannot be issued before its AuthorityEpoch observation"
            )
        if authority_epoch.next_known_transition_at is not None:
            transition = _parse_time(
                authority_epoch.next_known_transition_at,
                "AuthorityEpoch next_known_transition_at",
            )
            if _parse_time(ends, "valid_until") > transition:
                raise ActionLeaseContractError(
                    "lease cannot extend beyond the next known authority transition"
                )

        return cls(
            principal_id=principal,
            issuer_id=issuer,
            authorization_receipt_sha256=authorization_receipt,
            effect_intent_sha256=intent.effect_intent_sha256,
            enforcement_profile_sha256=enforcement.profile_sha256,
            authority_epoch_sha256=authority_epoch.authority_epoch_sha256,
            capability_id=intent.capability_id,
            capability_version=intent.capability_version,
            payload_sha256=intent.payload_sha256,
            effects_declared=intent.effects_declared,
            permissions_authorized=permissions,
            accepted_unenforced_effects=accepted_unenforced,
            issued_at=issued,
            valid_from=starts,
            valid_until=ends,
        )

    @classmethod
    def from_dict(cls, value: object) -> "ActionLease":
        if not isinstance(value, dict):
            raise ActionLeaseContractError(
                "ActionLease must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "principal_id",
            "issuer_id",
            "authorization_receipt_sha256",
            "effect_intent_sha256",
            "enforcement_profile_sha256",
            "authority_epoch_sha256",
            "capability_id",
            "capability_version",
            "payload_sha256",
            "effects_declared",
            "permissions_authorized",
            "accepted_unenforced_effects",
            "issued_at",
            "valid_from",
            "valid_until",
            "max_uses",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "action_lease_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise ActionLeaseContractError(
                f"ActionLease fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        tuple_fields = (
            "effects_declared",
            "permissions_authorized",
            "accepted_unenforced_effects",
        )
        parsed_tuples: dict[str, tuple[str, ...]] = {}
        for field in tuple_fields:
            raw = data[field]
            if not isinstance(raw, list):
                raise ActionLeaseContractError(
                    f"{field} must be an array"
                )
            parsed_tuples[field] = tuple(
                _require_text(item, f"{field} item")
                for item in raw
            )

        for field in (
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise ActionLeaseContractError(
                    f"{field} must be Boolean"
                )

        lease = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            principal_id=_require_text(
                data["principal_id"],
                "principal_id",
            ),
            issuer_id=_require_text(
                data["issuer_id"],
                "issuer_id",
            ),
            authorization_receipt_sha256=_require_sha256(
                data["authorization_receipt_sha256"],
                "authorization_receipt_sha256",
            ),
            effect_intent_sha256=_require_sha256(
                data["effect_intent_sha256"],
                "effect_intent_sha256",
            ),
            enforcement_profile_sha256=_require_sha256(
                data["enforcement_profile_sha256"],
                "enforcement_profile_sha256",
            ),
            authority_epoch_sha256=_require_sha256(
                data["authority_epoch_sha256"],
                "authority_epoch_sha256",
            ),
            capability_id=_require_text(
                data["capability_id"],
                "capability_id",
            ),
            capability_version=_require_text(
                data["capability_version"],
                "capability_version",
                maximum=128,
            ),
            payload_sha256=_require_sha256(
                data["payload_sha256"],
                "payload_sha256",
            ),
            effects_declared=parsed_tuples["effects_declared"],
            permissions_authorized=parsed_tuples[
                "permissions_authorized"
            ],
            accepted_unenforced_effects=parsed_tuples[
                "accepted_unenforced_effects"
            ],
            issued_at=_require_text(
                data["issued_at"],
                "issued_at",
                maximum=64,
            ),
            valid_from=_require_text(
                data["valid_from"],
                "valid_from",
                maximum=64,
            ),
            valid_until=_require_text(
                data["valid_until"],
                "valid_until",
                maximum=64,
            ),
            max_uses=data["max_uses"],
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )
        if data["action_lease_sha256"] != lease.action_lease_sha256:
            raise ActionLeaseContractError(
                "action_lease_sha256 does not match canonical ActionLease"
            )
        return lease


@dataclass(frozen=True, slots=True)
class ActionLeaseEvaluation:
    """Pure lease-usability decision. It cannot execute the leased action."""

    lease_sha256: str
    checked_at: str
    current_authority_epoch_sha256: str
    uses_consumed: int
    usable: bool
    reason: str
    action_authority: bool
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = ACTION_LEASE_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTION_LEASE_EVALUATION_SCHEMA_VERSION:
            raise ActionLeaseContractError(
                "unsupported ActionLease evaluation schema"
            )
        _require_sha256(self.lease_sha256, "lease_sha256")
        _require_sha256(
            self.current_authority_epoch_sha256,
            "current_authority_epoch_sha256",
        )
        canonical_checked = _canonical_time(
            self.checked_at,
            "checked_at",
        )
        if canonical_checked != self.checked_at:
            raise ActionLeaseContractError(
                "checked_at must use canonical UTC ISO-8601 form"
            )
        if isinstance(self.uses_consumed, bool) or not isinstance(
            self.uses_consumed,
            int,
        ) or self.uses_consumed < 0:
            raise ActionLeaseContractError(
                "uses_consumed must be an integer >= 0"
            )
        if self.action_authority is not self.usable:
            raise ActionLeaseContractError(
                "evaluation action_authority must match usability"
            )
        if self.execution_authority is not False:
            raise ActionLeaseContractError(
                "lease evaluation cannot carry execution authority"
            )
        if self.effect_performed is not False:
            raise ActionLeaseContractError(
                "lease evaluation cannot claim an effect was performed"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lease_sha256": self.lease_sha256,
            "checked_at": self.checked_at,
            "current_authority_epoch_sha256": (
                self.current_authority_epoch_sha256
            ),
            "uses_consumed": self.uses_consumed,
            "usable": self.usable,
            "reason": self.reason,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }


def evaluate_action_lease(
    *,
    lease: ActionLease,
    checked_at: str,
    current_authority_epoch_sha256: str,
    uses_consumed: int,
) -> ActionLeaseEvaluation:
    """Evaluate lease currency without performing or authorizing execution."""

    checked = _canonical_time(checked_at, "checked_at")
    current_epoch = _require_sha256(
        current_authority_epoch_sha256,
        "current_authority_epoch_sha256",
    )
    if isinstance(uses_consumed, bool) or not isinstance(
        uses_consumed,
        int,
    ) or uses_consumed < 0:
        raise ActionLeaseContractError(
            "uses_consumed must be an integer >= 0"
        )

    now = _parse_time(checked, "checked_at")
    starts = _parse_time(lease.valid_from, "valid_from")
    ends = _parse_time(lease.valid_until, "valid_until")

    usable = True
    reason = "lease_current"
    if current_epoch != lease.authority_epoch_sha256:
        usable = False
        reason = "authority_epoch_changed"
    elif now < starts:
        usable = False
        reason = "lease_not_yet_valid"
    elif now >= ends:
        usable = False
        reason = "lease_expired"
    elif uses_consumed >= lease.max_uses:
        usable = False
        reason = "lease_consumed"

    return ActionLeaseEvaluation(
        lease_sha256=lease.action_lease_sha256,
        checked_at=checked,
        current_authority_epoch_sha256=current_epoch,
        uses_consumed=uses_consumed,
        usable=usable,
        reason=reason,
        action_authority=usable,
    )
