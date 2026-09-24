"""Canonical authority-state snapshot for PhiOS.

AuthorityEpoch binds one principal to one exact, reconstructed authority state
under one policy and one known event set. It is descriptive state, not a grant,
not an action lease, and not execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from phios.mandala import (
    AuthoritativeAuthorityEvent,
    AuthorityEventKind,
    AuthorityProjection,
    AuthorityProjectionError,
)

AUTHORITY_EPOCH_SCHEMA_VERSION = "phios.authority_epoch.v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AuthorityEpochContractError(ValueError):
    """Raised when an AuthorityEpoch violates the canonical contract."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise AuthorityEpochContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise AuthorityEpochContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise AuthorityEpochContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise AuthorityEpochContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _parse_time(value: object, field: str) -> datetime:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorityEpochContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorityEpochContractError(
            f"{field} must include a timezone offset"
        )
    return parsed.astimezone(UTC)


def _canonical_time(value: object, field: str) -> str:
    return _parse_time(value, field).isoformat()


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
        raise AuthorityEpochContractError(
            "authority epoch payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_text_tuple(
    values: tuple[str, ...],
    field: str,
) -> tuple[str, ...]:
    normalized = tuple(
        _require_text(item, f"{field} item")
        for item in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise AuthorityEpochContractError(
            f"{field} must be sorted and unique"
        )
    return normalized


def _event_set_sha256(
    events: tuple[AuthoritativeAuthorityEvent, ...],
    kind: AuthorityEventKind,
) -> str:
    selected = [
        event.to_dict()
        for event in sorted(events, key=lambda item: item.sequence)
        if event.kind is kind
    ]
    return _canonical_sha256(selected)


def _next_known_transition(
    *,
    events: tuple[AuthoritativeAuthorityEvent, ...],
    observed_at: str,
    active_grant_event_ids: tuple[str, ...],
) -> str | None:
    observed = _parse_time(observed_at, "observed_at")
    active_ids = set(active_grant_event_ids)
    candidates: list[datetime] = []

    for event in events:
        effective = _parse_time(event.effective_at, "event effective_at")
        if effective > observed:
            candidates.append(effective)
        if (
            event.event_id in active_ids
            and event.expires_at is not None
        ):
            expires = _parse_time(event.expires_at, "event expires_at")
            if expires > observed:
                candidates.append(expires)

    if not candidates:
        return None
    return min(candidates).astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class AuthorityEpoch:
    """Immutable description of one exact authority state.

    The reconstructed grants field describes authority that existed at the
    observation point according to the supplied authoritative event history.
    This object cannot itself grant, lease, or execute that authority.
    """

    principal_id: str
    observed_at: str
    policy_sha256: str
    ceiling: tuple[str, ...]
    grants: tuple[str, ...]
    authority_sources: tuple[str, ...]
    known_event_ids: tuple[str, ...]
    applied_event_ids: tuple[str, ...]
    active_grant_event_ids: tuple[str, ...]
    source_events_sha256: str
    grant_set_sha256: str
    revocation_set_sha256: str
    projection_sha256: str
    authority_context_sha256: str
    next_known_transition_at: str | None
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = AUTHORITY_EPOCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AUTHORITY_EPOCH_SCHEMA_VERSION:
            raise AuthorityEpochContractError(
                f"unsupported AuthorityEpoch schema: {self.schema_version}"
            )
        _require_text(self.principal_id, "principal_id")
        canonical_observed = _canonical_time(
            self.observed_at,
            "observed_at",
        )
        if canonical_observed != self.observed_at:
            raise AuthorityEpochContractError(
                "observed_at must use canonical UTC ISO-8601 form"
            )
        _require_sha256(self.policy_sha256, "policy_sha256")

        _canonical_text_tuple(self.ceiling, "ceiling")
        _canonical_text_tuple(self.grants, "grants")
        if not set(self.grants).issubset(set(self.ceiling)):
            raise AuthorityEpochContractError(
                "grants must remain within the authority ceiling"
            )
        _canonical_text_tuple(
            self.authority_sources,
            "authority_sources",
        )
        _canonical_text_tuple(
            self.known_event_ids,
            "known_event_ids",
        )
        _canonical_text_tuple(
            self.applied_event_ids,
            "applied_event_ids",
        )
        _canonical_text_tuple(
            self.active_grant_event_ids,
            "active_grant_event_ids",
        )
        if not set(self.applied_event_ids).issubset(
            set(self.known_event_ids)
        ):
            raise AuthorityEpochContractError(
                "applied_event_ids must be a subset of known_event_ids"
            )
        if not set(self.active_grant_event_ids).issubset(
            set(self.applied_event_ids)
        ):
            raise AuthorityEpochContractError(
                "active_grant_event_ids must be a subset of applied_event_ids"
            )

        for field, digest in (
            ("source_events_sha256", self.source_events_sha256),
            ("grant_set_sha256", self.grant_set_sha256),
            ("revocation_set_sha256", self.revocation_set_sha256),
            ("projection_sha256", self.projection_sha256),
            ("authority_context_sha256", self.authority_context_sha256),
        ):
            _require_sha256(digest, field)

        expected_context = _canonical_sha256(
            {
                "ceiling": list(self.ceiling),
                "grants": list(self.grants),
            }
        )
        if self.authority_context_sha256 != expected_context:
            raise AuthorityEpochContractError(
                "authority_context_sha256 does not match ceiling and grants"
            )

        if self.next_known_transition_at is not None:
            transition = _canonical_time(
                self.next_known_transition_at,
                "next_known_transition_at",
            )
            if transition != self.next_known_transition_at:
                raise AuthorityEpochContractError(
                    "next_known_transition_at must use canonical UTC form"
                )
            if _parse_time(
                transition,
                "next_known_transition_at",
            ) <= _parse_time(self.observed_at, "observed_at"):
                raise AuthorityEpochContractError(
                    "next_known_transition_at must be later than observed_at"
                )

        if self.effect_performed is not False:
            raise AuthorityEpochContractError(
                "AuthorityEpoch cannot claim an effect was performed"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise AuthorityEpochContractError(
                "AuthorityEpoch cannot itself carry operational, action, "
                "or execution authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "principal_id": self.principal_id,
            "observed_at": self.observed_at,
            "policy_sha256": self.policy_sha256,
            "ceiling": list(self.ceiling),
            "grants": list(self.grants),
            "authority_sources": list(self.authority_sources),
            "known_event_ids": list(self.known_event_ids),
            "applied_event_ids": list(self.applied_event_ids),
            "active_grant_event_ids": list(
                self.active_grant_event_ids
            ),
            "source_events_sha256": self.source_events_sha256,
            "grant_set_sha256": self.grant_set_sha256,
            "revocation_set_sha256": self.revocation_set_sha256,
            "projection_sha256": self.projection_sha256,
            "authority_context_sha256": self.authority_context_sha256,
            "next_known_transition_at": self.next_known_transition_at,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def authority_epoch_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["authority_epoch_sha256"] = self.authority_epoch_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        principal_id: str,
        policy_sha256: str,
        ceiling: tuple[str, ...],
        events: tuple[AuthoritativeAuthorityEvent, ...],
        observed_at: str,
    ) -> "AuthorityEpoch":
        principal = _require_text(principal_id, "principal_id")
        policy = _require_sha256(policy_sha256, "policy_sha256")
        observed = _canonical_time(observed_at, "observed_at")

        ordered_events = tuple(
            sorted(events, key=lambda item: item.sequence)
        )
        event_ids = tuple(event.event_id for event in ordered_events)
        if len(set(event_ids)) != len(event_ids):
            raise AuthorityEpochContractError(
                "authority event IDs must be unique"
            )

        try:
            projection = AuthorityProjection.project(
                ceiling=ceiling,
                events=ordered_events,
                observed_at=observed,
            )
        except AuthorityProjectionError as exc:
            raise AuthorityEpochContractError(str(exc)) from exc

        known_event_ids = tuple(sorted(event_ids))
        applied_event_ids = tuple(sorted(projection.source_event_ids))
        active_grant_event_ids = tuple(
            sorted(projection.active_grant_event_ids)
        )
        sources = tuple(
            sorted(
                {
                    _require_text(
                        event.authority_source,
                        "event authority_source",
                    )
                    for event in ordered_events
                }
            )
        )
        canonical_ceiling = tuple(sorted(set(projection.ceiling)))
        canonical_grants = tuple(sorted(set(projection.grants)))

        return cls(
            principal_id=principal,
            observed_at=projection.observed_at,
            policy_sha256=policy,
            ceiling=canonical_ceiling,
            grants=canonical_grants,
            authority_sources=sources,
            known_event_ids=known_event_ids,
            applied_event_ids=applied_event_ids,
            active_grant_event_ids=active_grant_event_ids,
            source_events_sha256=projection.source_events_sha256,
            grant_set_sha256=_event_set_sha256(
                ordered_events,
                AuthorityEventKind.GRANT,
            ),
            revocation_set_sha256=_event_set_sha256(
                ordered_events,
                AuthorityEventKind.REVOKE,
            ),
            projection_sha256=projection.projection_sha256,
            authority_context_sha256=_canonical_sha256(
                {
                    "ceiling": list(canonical_ceiling),
                    "grants": list(canonical_grants),
                }
            ),
            next_known_transition_at=_next_known_transition(
                events=ordered_events,
                observed_at=projection.observed_at,
                active_grant_event_ids=active_grant_event_ids,
            ),
        )

    @classmethod
    def from_dict(cls, value: object) -> "AuthorityEpoch":
        if not isinstance(value, dict):
            raise AuthorityEpochContractError(
                "AuthorityEpoch must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "principal_id",
            "observed_at",
            "policy_sha256",
            "ceiling",
            "grants",
            "authority_sources",
            "known_event_ids",
            "applied_event_ids",
            "active_grant_event_ids",
            "source_events_sha256",
            "grant_set_sha256",
            "revocation_set_sha256",
            "projection_sha256",
            "authority_context_sha256",
            "next_known_transition_at",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "authority_epoch_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise AuthorityEpochContractError(
                f"AuthorityEpoch fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        tuple_fields = (
            "ceiling",
            "grants",
            "authority_sources",
            "known_event_ids",
            "applied_event_ids",
            "active_grant_event_ids",
        )
        parsed_tuples: dict[str, tuple[str, ...]] = {}
        for field in tuple_fields:
            raw = data[field]
            if not isinstance(raw, list):
                raise AuthorityEpochContractError(
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
                raise AuthorityEpochContractError(
                    f"{field} must be Boolean"
                )

        transition_raw = data["next_known_transition_at"]
        if transition_raw is not None and not isinstance(
            transition_raw,
            str,
        ):
            raise AuthorityEpochContractError(
                "next_known_transition_at must be a string or null"
            )

        epoch = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            principal_id=_require_text(
                data["principal_id"],
                "principal_id",
            ),
            observed_at=_require_text(
                data["observed_at"],
                "observed_at",
                maximum=64,
            ),
            policy_sha256=_require_sha256(
                data["policy_sha256"],
                "policy_sha256",
            ),
            ceiling=parsed_tuples["ceiling"],
            grants=parsed_tuples["grants"],
            authority_sources=parsed_tuples["authority_sources"],
            known_event_ids=parsed_tuples["known_event_ids"],
            applied_event_ids=parsed_tuples["applied_event_ids"],
            active_grant_event_ids=parsed_tuples[
                "active_grant_event_ids"
            ],
            source_events_sha256=_require_sha256(
                data["source_events_sha256"],
                "source_events_sha256",
            ),
            grant_set_sha256=_require_sha256(
                data["grant_set_sha256"],
                "grant_set_sha256",
            ),
            revocation_set_sha256=_require_sha256(
                data["revocation_set_sha256"],
                "revocation_set_sha256",
            ),
            projection_sha256=_require_sha256(
                data["projection_sha256"],
                "projection_sha256",
            ),
            authority_context_sha256=_require_sha256(
                data["authority_context_sha256"],
                "authority_context_sha256",
            ),
            next_known_transition_at=transition_raw,
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )
        if data["authority_epoch_sha256"] != epoch.authority_epoch_sha256:
            raise AuthorityEpochContractError(
                "authority_epoch_sha256 does not match canonical AuthorityEpoch"
            )
        return epoch
