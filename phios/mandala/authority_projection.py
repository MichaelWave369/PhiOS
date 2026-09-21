from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .contracts import AuthorityContext, canonical_digest


class AuthorityProjectionError(ValueError):
    """Raised when authoritative replay inputs are malformed or exceed the ceiling."""


class AuthorityEventKind(StrEnum):
    GRANT = "grant"
    REVOKE = "revoke"


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorityProjectionError(f"{label} must be a non-empty string")
    return value.strip()


def _utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthorityProjectionError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AuthorityProjectionError(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, kw_only=True)
class AuthoritativeAuthorityEvent:
    """One already-authoritative grant/revoke event supplied to read-only replay."""

    event_id: str
    sequence: int
    kind: AuthorityEventKind
    permission: str
    authority_source: str
    effective_at: str
    expires_at: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.event_id, "event_id")
        _require_nonempty(self.permission, "permission")
        _require_nonempty(self.authority_source, "authority_source")
        if not isinstance(self.kind, AuthorityEventKind):
            raise AuthorityProjectionError("kind must be a canonical AuthorityEventKind")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise AuthorityProjectionError("sequence must be an integer >= 0")
        effective = _utc(self.effective_at, "effective_at")
        if self.kind is AuthorityEventKind.REVOKE and self.expires_at is not None:
            raise AuthorityProjectionError("revoke events cannot carry expires_at")
        if self.expires_at is not None:
            expires = _utc(self.expires_at, "expires_at")
            if expires <= effective:
                raise AuthorityProjectionError("expires_at must be later than effective_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "permission": self.permission,
            "authority_source": self.authority_source,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, kw_only=True)
class AuthorityProjectionResult:
    """Deterministic present-tense authority reconstructed from authoritative events."""

    observed_at: str
    ceiling: tuple[str, ...]
    grants: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    active_grant_event_ids: tuple[str, ...]
    source_events_sha256: str
    projection_sha256: str

    def to_authority_context(self) -> AuthorityContext:
        return AuthorityContext(ceiling=self.ceiling, grants=self.grants)

    def to_dict(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at,
            "ceiling": list(self.ceiling),
            "grants": list(self.grants),
            "source_event_ids": list(self.source_event_ids),
            "active_grant_event_ids": list(self.active_grant_event_ids),
            "source_events_sha256": self.source_events_sha256,
            "projection_sha256": self.projection_sha256,
        }


class AuthorityProjection:
    """Read-only replay. It cannot create authority beyond supplied authoritative events."""

    @staticmethod
    def project(
        *,
        ceiling: tuple[str, ...],
        events: tuple[AuthoritativeAuthorityEvent, ...],
        observed_at: str,
    ) -> AuthorityProjectionResult:
        observed = _utc(observed_at, "observed_at")
        normalized_ceiling = tuple(
            sorted({_require_nonempty(item, "ceiling permission") for item in ceiling})
        )
        ceiling_set = set(normalized_ceiling)

        ordered = tuple(sorted(events, key=lambda item: item.sequence))
        if len({item.sequence for item in ordered}) != len(ordered):
            raise AuthorityProjectionError("authority event sequences must be unique")

        prior_effective: datetime | None = None
        for event in ordered:
            effective = _utc(event.effective_at, "effective_at")
            if prior_effective is not None and effective < prior_effective:
                raise AuthorityProjectionError(
                    "authority event effective_at must be monotonic with sequence"
                )
            prior_effective = effective
            if event.permission not in ceiling_set:
                raise AuthorityProjectionError("authority event permission exceeds the frozen ceiling")

        event_payload = [event.to_dict() for event in ordered]
        source_events_sha256 = canonical_digest(event_payload)

        last_grant: dict[str, AuthoritativeAuthorityEvent] = {}
        applied_event_ids: list[str] = []
        for event in ordered:
            if _utc(event.effective_at, "effective_at") > observed:
                continue
            applied_event_ids.append(event.event_id)
            if event.kind is AuthorityEventKind.REVOKE:
                last_grant.pop(event.permission, None)
                continue
            last_grant[event.permission] = event

        active_permissions: list[str] = []
        active_grant_event_ids: list[str] = []
        for permission, grant in sorted(last_grant.items()):
            if grant.expires_at is not None and _utc(grant.expires_at, "expires_at") <= observed:
                continue
            active_permissions.append(permission)
            active_grant_event_ids.append(grant.event_id)

        body = {
            "schema": "phios.authority_projection.v0.1",
            "observed_at": observed.isoformat(),
            "ceiling": list(normalized_ceiling),
            "grants": active_permissions,
            "source_event_ids": applied_event_ids,
            "active_grant_event_ids": active_grant_event_ids,
            "source_events_sha256": source_events_sha256,
        }
        return AuthorityProjectionResult(
            observed_at=observed.isoformat(),
            ceiling=normalized_ceiling,
            grants=tuple(active_permissions),
            source_event_ids=tuple(applied_event_ids),
            active_grant_event_ids=tuple(active_grant_event_ids),
            source_events_sha256=source_events_sha256,
            projection_sha256=canonical_digest(body),
        )
