"""Ephemeral local PhiVessel ↔ PhiOS host handshake for v0.38.

The handshake establishes only a short-lived transport session. It does not
authenticate the asserted PhiVessel identity and it does not grant policy,
operational, action, or execution authority.

Action authority continues to come only from an already-issued ActionLease.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable

PHIVESSEL_HANDSHAKE_SCHEMA_VERSION = "phios.phivessel_handshake.v0.38"
PHIVESSEL_SESSION_SCHEMA_VERSION = "phios.phivessel_session.v0.38"
PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION = "PV-PHIOS-HANDSHAKE-0.1"

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SESSION_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")


class PhiVesselHandshakeError(ValueError):
    """Raised when local PhiVessel transport admission fails closed."""


class PhiVesselSessionOperation(StrEnum):
    OBSERVE = "OBSERVE"
    PROPOSE = "PROPOSE"
    EXECUTE = "EXECUTE"


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
        raise PhiVesselHandshakeError(
            "handshake payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PhiVesselHandshakeError(
            "handshake clock must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PhiVesselHandshakeError(
            "session timestamp must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PhiVesselHandshakeError(
            "session timestamp must be timezone-aware"
        )
    return parsed.astimezone(UTC)


def _require_client_id(value: object) -> str:
    if not isinstance(value, str) or _CLIENT_ID_RE.fullmatch(value) is None:
        raise PhiVesselHandshakeError(
            "client_instance_id must be a bounded canonical identifier"
        )
    return value


def _require_nonce(value: object) -> str:
    if not isinstance(value, str) or _NONCE_RE.fullmatch(value) is None:
        raise PhiVesselHandshakeError(
            "client_nonce must be 16-128 URL-safe characters"
        )
    return value


def _versions(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values or len(values) > 8:
        raise PhiVesselHandshakeError(
            "supported bridge versions must contain 1-8 values"
        )
    normalized: list[str] = []
    for value in values:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 64
            or any(ord(char) < 32 for char in value)
        ):
            raise PhiVesselHandshakeError(
                "supported bridge version is invalid"
            )
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _operations(
    values: tuple[PhiVesselSessionOperation, ...],
) -> tuple[PhiVesselSessionOperation, ...]:
    if not values or len(values) > 3:
        raise PhiVesselHandshakeError(
            "requested operations must contain 1-3 values"
        )
    if any(
        not isinstance(value, PhiVesselSessionOperation)
        for value in values
    ):
        raise PhiVesselHandshakeError(
            "requested operation is unsupported"
        )
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class PhiVesselHostSession:
    session_id: str
    client_instance_id: str
    client_nonce: str
    server_instance_id: str
    selected_bridge_version: str
    granted_operations: tuple[PhiVesselSessionOperation, ...]
    issued_at: str
    expires_at: str
    token_sha256: str
    client_identity_authenticated: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = PHIVESSEL_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVESSEL_SESSION_SCHEMA_VERSION:
            raise PhiVesselHandshakeError(
                "unsupported PhiVessel session schema"
            )
        if not self.session_id.startswith("pvs:"):
            raise PhiVesselHandshakeError("session_id is malformed")
        _require_client_id(self.client_instance_id)
        _require_nonce(self.client_nonce)
        if not self.server_instance_id.startswith("pvh:"):
            raise PhiVesselHandshakeError(
                "server_instance_id is malformed"
            )
        _operations(self.granted_operations)
        if (
            not isinstance(self.token_sha256, str)
            or _SESSION_TOKEN_RE.fullmatch(self.token_sha256) is None
        ):
            raise PhiVesselHandshakeError(
                "session token digest is malformed"
            )
        issued = _parse_time(self.issued_at)
        expires = _parse_time(self.expires_at)
        if expires <= issued:
            raise PhiVesselHandshakeError(
                "session expiry must follow issue time"
            )
        if self.client_identity_authenticated is not False:
            raise PhiVesselHandshakeError(
                "v0.38 cannot claim authenticated client identity"
            )
        if any(
            (
                self.policy_authority,
                self.operational_authority,
                self.action_authority,
                self.execution_authority,
                self.effect_performed,
            )
        ):
            raise PhiVesselHandshakeError(
                "transport session cannot carry authority or effects"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "client_instance_id": self.client_instance_id,
            "client_nonce": self.client_nonce,
            "server_instance_id": self.server_instance_id,
            "selected_bridge_version": self.selected_bridge_version,
            "granted_operations": [
                item.value for item in self.granted_operations
            ],
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "client_identity_authenticated": (
                self.client_identity_authenticated
            ),
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }


@dataclass(frozen=True, slots=True)
class PhiVesselHandshakeResult:
    handshake_protocol_version: str
    selected_bridge_version: str
    server_identity: str
    server_instance_id: str
    client_instance_id: str
    client_nonce: str
    granted_operations: tuple[PhiVesselSessionOperation, ...]
    session_id: str
    session_token: str
    issued_at: str
    expires_at: str
    client_identity_authenticated: bool = False
    transport_session_only: bool = True
    action_lease_still_required_for_execution: bool = True
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = PHIVESSEL_HANDSHAKE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PHIVESSEL_HANDSHAKE_SCHEMA_VERSION:
            raise PhiVesselHandshakeError(
                "unsupported PhiVessel handshake schema"
            )
        if self.handshake_protocol_version != (
            PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION
        ):
            raise PhiVesselHandshakeError(
                "unsupported handshake protocol version"
            )
        if _SESSION_TOKEN_RE.fullmatch(self.session_token) is None:
            raise PhiVesselHandshakeError(
                "session_token must be a 256-bit lowercase hex token"
            )
        if self.client_identity_authenticated is not False:
            raise PhiVesselHandshakeError(
                "v0.38 cannot claim authenticated client identity"
            )
        if self.transport_session_only is not True:
            raise PhiVesselHandshakeError(
                "handshake must remain transport-session only"
            )
        if self.action_lease_still_required_for_execution is not True:
            raise PhiVesselHandshakeError(
                "handshake cannot replace ActionLease authority"
            )
        if any(
            (
                self.policy_authority,
                self.operational_authority,
                self.action_authority,
                self.execution_authority,
                self.effect_performed,
            )
        ):
            raise PhiVesselHandshakeError(
                "handshake result cannot carry authority or effects"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "handshake_protocol_version": (
                self.handshake_protocol_version
            ),
            "selected_bridge_version": self.selected_bridge_version,
            "server_identity": self.server_identity,
            "server_instance_id": self.server_instance_id,
            "client_instance_id": self.client_instance_id,
            "client_nonce": self.client_nonce,
            "granted_operations": [
                item.value for item in self.granted_operations
            ],
            "session_id": self.session_id,
            "session_token": self.session_token,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "client_identity_authenticated": (
                self.client_identity_authenticated
            ),
            "transport_session_only": self.transport_session_only,
            "action_lease_still_required_for_execution": (
                self.action_lease_still_required_for_execution
            ),
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }


class PhiVesselHostHandshakeService:
    """Issue and validate ephemeral local transport sessions."""

    def __init__(
        self,
        *,
        bridge_version: str,
        available_operations: tuple[PhiVesselSessionOperation, ...],
        session_ttl_seconds: int = 300,
        server_identity: str = "phios:ghostwalk-local-host",
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if (
            not isinstance(session_ttl_seconds, int)
            or isinstance(session_ttl_seconds, bool)
            or session_ttl_seconds < 30
            or session_ttl_seconds > 900
        ):
            raise PhiVesselHandshakeError(
                "session_ttl_seconds must be 30-900"
            )
        if not bridge_version or len(bridge_version) > 64:
            raise PhiVesselHandshakeError("bridge_version is invalid")
        if (
            not server_identity
            or len(server_identity) > 256
            or any(ord(char) < 32 for char in server_identity)
        ):
            raise PhiVesselHandshakeError("server_identity is invalid")
        self.bridge_version = bridge_version
        self.available_operations = _operations(available_operations)
        self.session_ttl_seconds = session_ttl_seconds
        self.server_identity = server_identity
        self.server_instance_id = "pvh:" + secrets.token_hex(12)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_hex(32))
        self._sessions: dict[str, PhiVesselHostSession] = {}
        self._lock = threading.RLock()

    def handshake(
        self,
        *,
        client_instance_id: str,
        client_nonce: str,
        supported_bridge_versions: tuple[str, ...],
        requested_operations: tuple[PhiVesselSessionOperation, ...],
    ) -> PhiVesselHandshakeResult:
        client_id = _require_client_id(client_instance_id)
        nonce = _require_nonce(client_nonce)
        versions = _versions(supported_bridge_versions)
        requested = _operations(requested_operations)
        if self.bridge_version not in versions:
            raise PhiVesselHandshakeError(
                "no mutually supported PhiVessel bridge version"
            )
        granted = tuple(
            item for item in requested
            if item in set(self.available_operations)
        )
        if not granted:
            raise PhiVesselHandshakeError(
                "no requested PhiVessel operation is available"
            )

        now = self._now()
        expires = now + timedelta(seconds=self.session_ttl_seconds)
        token = self._token_factory()
        if _SESSION_TOKEN_RE.fullmatch(token) is None:
            raise PhiVesselHandshakeError(
                "session token factory returned an invalid token"
            )
        token_sha = hashlib.sha256(token.encode("ascii")).hexdigest()
        session_id = "pvs:" + _canonical_sha256(
            {
                "server_instance_id": self.server_instance_id,
                "client_instance_id": client_id,
                "client_nonce": nonce,
                "selected_bridge_version": self.bridge_version,
                "granted_operations": [
                    item.value for item in granted
                ],
                "issued_at": _canonical_time(now),
                "token_sha256": token_sha,
            }
        )[:24]
        session = PhiVesselHostSession(
            session_id=session_id,
            client_instance_id=client_id,
            client_nonce=nonce,
            server_instance_id=self.server_instance_id,
            selected_bridge_version=self.bridge_version,
            granted_operations=granted,
            issued_at=_canonical_time(now),
            expires_at=_canonical_time(expires),
            token_sha256=token_sha,
        )
        with self._lock:
            self._prune(now)
            self._sessions[session_id] = session

        return PhiVesselHandshakeResult(
            handshake_protocol_version=(
                PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION
            ),
            selected_bridge_version=self.bridge_version,
            server_identity=self.server_identity,
            server_instance_id=self.server_instance_id,
            client_instance_id=client_id,
            client_nonce=nonce,
            granted_operations=granted,
            session_id=session_id,
            session_token=token,
            issued_at=session.issued_at,
            expires_at=session.expires_at,
        )

    def validate(
        self,
        *,
        session_id: str,
        session_token: str,
        operation: PhiVesselSessionOperation,
    ) -> PhiVesselHostSession:
        if (
            not isinstance(session_id, str)
            or not session_id.startswith("pvs:")
            or len(session_id) != 28
        ):
            raise PhiVesselHandshakeError("session_id is malformed")
        if (
            not isinstance(session_token, str)
            or _SESSION_TOKEN_RE.fullmatch(session_token) is None
        ):
            raise PhiVesselHandshakeError("session_token is malformed")
        if not isinstance(operation, PhiVesselSessionOperation):
            raise PhiVesselHandshakeError("session operation is invalid")

        now = self._now()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(session_id)
            if session is None:
                raise PhiVesselHandshakeError(
                    "PhiVessel session is absent or expired"
                )
            actual = hashlib.sha256(
                session_token.encode("ascii")
            ).hexdigest()
            if not hmac.compare_digest(actual, session.token_sha256):
                raise PhiVesselHandshakeError(
                    "PhiVessel session token does not match"
                )
            if operation not in set(session.granted_operations):
                raise PhiVesselHandshakeError(
                    "PhiVessel operation was not negotiated for this session"
                )
            return session

    def _prune(self, now: datetime) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if _parse_time(session.expires_at) <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise PhiVesselHandshakeError(
                "handshake clock must return datetime"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise PhiVesselHandshakeError(
                "handshake clock must be timezone-aware"
            )
        return value.astimezone(UTC)


__all__ = [
    "PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION",
    "PHIVESSEL_HANDSHAKE_SCHEMA_VERSION",
    "PHIVESSEL_SESSION_SCHEMA_VERSION",
    "PhiVesselHandshakeError",
    "PhiVesselHandshakeResult",
    "PhiVesselHostHandshakeService",
    "PhiVesselHostSession",
    "PhiVesselSessionOperation",
]
