"""Governed inbound/outbound API-key boundary for PhiOS.

API keys are capabilities for authentication, not authority grants. Inbound keys prove
possession for a configured audience. Outbound keys are resolved only at use time from
an external secret source and are never written to receipts or normal object reprs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Mapping

API_KEY_BOUNDARY_SCHEMA_VERSION = "phios.api_key_boundary.v0.1"
API_KEY_AUTH_RECEIPT_SCHEMA_VERSION = "phios.api_key_auth_receipt.v0.1"
API_KEY_LEASE_RECEIPT_SCHEMA_VERSION = "phios.api_key_lease_receipt.v0.1"

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]+$")


class ApiKeyContractError(ValueError):
    """Raised when an API-key contract is invalid or unavailable."""


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
        raise ApiKeyContractError("API-key metadata must be canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _secret_sha256(secret: str) -> str:
    if not isinstance(secret, str) or not secret:
        raise ApiKeyContractError("API key must be a non-empty string")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiKeyContractError(f"{label} must be non-empty")
    return value.strip()


def _normalize_scopes(scopes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({_require_text(scope, "scope") for scope in scopes}))


@dataclass(frozen=True, slots=True)
class InboundApiKeySpec:
    """Metadata plus one-way digest for a key presented to PhiOS."""

    key_id: str
    audience: str
    secret_sha256: str = field(repr=False)
    scopes: tuple[str, ...] = ()

    @classmethod
    def from_secret(
        cls,
        *,
        key_id: str,
        audience: str,
        secret: str,
        scopes: tuple[str, ...] = (),
    ) -> "InboundApiKeySpec":
        return cls(
            key_id=_require_text(key_id, "key_id"),
            audience=_require_text(audience, "audience"),
            secret_sha256=_secret_sha256(secret),
            scopes=_normalize_scopes(scopes),
        ).normalized()

    @classmethod
    def from_digest(
        cls,
        *,
        key_id: str,
        audience: str,
        secret_sha256: str,
        scopes: tuple[str, ...] = (),
    ) -> "InboundApiKeySpec":
        return cls(
            key_id=key_id,
            audience=audience,
            secret_sha256=secret_sha256,
            scopes=scopes,
        ).normalized()

    def normalized(self) -> "InboundApiKeySpec":
        digest = _require_text(self.secret_sha256, "secret_sha256").lower()
        if len(digest) != 64:
            raise ApiKeyContractError("secret_sha256 must be SHA-256 hex")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ApiKeyContractError("secret_sha256 must be SHA-256 hex") from exc
        return InboundApiKeySpec(
            key_id=_require_text(self.key_id, "key_id"),
            audience=_require_text(self.audience, "audience"),
            secret_sha256=digest,
            scopes=_normalize_scopes(self.scopes),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": API_KEY_BOUNDARY_SCHEMA_VERSION,
            "direction": "inbound",
            "key_id": self.key_id,
            "audience": self.audience,
            "scopes": list(self.scopes),
            "credential_material": "sha256_digest_configured",
        }

    @property
    def public_contract_sha256(self) -> str:
        return _sha256(self.public_dict())


@dataclass(frozen=True, slots=True)
class OutboundApiKeySpec:
    """Reference to a secret that PhiOS may use for one provider."""

    key_id: str
    provider: str
    environment_variable: str
    header_name: str = "Authorization"
    header_prefix: str = "Bearer"
    scopes: tuple[str, ...] = ()

    def normalized(self) -> "OutboundApiKeySpec":
        env = _require_text(self.environment_variable, "environment_variable")
        if not _ENV_NAME.fullmatch(env):
            raise ApiKeyContractError(
                "environment_variable must be an uppercase environment name"
            )
        header_name = _require_text(self.header_name, "header_name")
        if not _HEADER_NAME.fullmatch(header_name):
            raise ApiKeyContractError("header_name is invalid")
        return OutboundApiKeySpec(
            key_id=_require_text(self.key_id, "key_id"),
            provider=_require_text(self.provider, "provider"),
            environment_variable=env,
            header_name=header_name,
            header_prefix=self.header_prefix.strip(),
            scopes=_normalize_scopes(self.scopes),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": API_KEY_BOUNDARY_SCHEMA_VERSION,
            "direction": "outbound",
            "key_id": self.key_id,
            "provider": self.provider,
            "header_name": self.header_name,
            "header_prefix": bool(self.header_prefix),
            "scopes": list(self.scopes),
            "secret_source": "environment",
        }

    @property
    def public_contract_sha256(self) -> str:
        return _sha256(self.public_dict())


@dataclass(frozen=True, slots=True)
class ApiKeyAuthReceipt:
    schema: str
    receipt_id: str
    key_id: str
    audience: str
    scopes: tuple[str, ...]
    status: str
    reason: str
    public_contract_sha256: str
    credential_exposed: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    @property
    def authenticated(self) -> bool:
        return self.status == "AUTHENTICATED"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "key_id": self.key_id,
            "audience": self.audience,
            "scopes": list(self.scopes),
            "status": self.status,
            "reason": self.reason,
            "public_contract_sha256": self.public_contract_sha256,
            "credential_exposed": self.credential_exposed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class ApiKeyLeaseReceipt:
    schema: str
    receipt_id: str
    key_id: str
    provider: str
    scopes: tuple[str, ...]
    header_name: str
    status: str
    reason: str
    public_contract_sha256: str
    secret_source: str
    credential_exposed: bool
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "key_id": self.key_id,
            "provider": self.provider,
            "scopes": list(self.scopes),
            "header_name": self.header_name,
            "status": self.status,
            "reason": self.reason,
            "public_contract_sha256": self.public_contract_sha256,
            "secret_source": self.secret_source,
            "credential_exposed": self.credential_exposed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class OutboundApiKeyLease:
    """Ephemeral credential lease. Secret material is deliberately non-serializable."""

    key_id: str
    provider: str
    header_name: str
    header_prefix: str
    scopes: tuple[str, ...]
    receipt: ApiKeyLeaseReceipt
    _secret: str = field(repr=False, compare=False)

    def authorization_headers(
        self,
        existing: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers = dict(existing or {})
        if any(name.lower() == self.header_name.lower() for name in headers):
            raise ApiKeyContractError(
                "credential header already exists; refusing ambiguous overwrite"
            )
        value = (
            f"{self.header_prefix} {self._secret}"
            if self.header_prefix
            else self._secret
        )
        headers[self.header_name] = value
        return headers

    def metadata(self) -> dict[str, object]:
        return {
            "key_id": self.key_id,
            "provider": self.provider,
            "header_name": self.header_name,
            "scopes": list(self.scopes),
            "receipt_sha256": self.receipt.receipt_sha256,
            "secret": "[REDACTED]",
        }


class ApiKeyBoundary:
    """Separate inbound authentication from outbound secret use."""

    def __init__(
        self,
        *,
        environment_getter: Callable[[str], str | None] | None = None,
    ) -> None:
        self._inbound: dict[str, InboundApiKeySpec] = {}
        self._outbound: dict[str, OutboundApiKeySpec] = {}
        self._environment_getter = environment_getter or os.environ.get

    def register_inbound(self, spec: InboundApiKeySpec) -> None:
        normalized = spec.normalized()
        self._register_unique(normalized.key_id)
        self._inbound[normalized.key_id] = normalized

    def register_outbound(self, spec: OutboundApiKeySpec) -> None:
        normalized = spec.normalized()
        self._register_unique(normalized.key_id)
        self._outbound[normalized.key_id] = normalized

    def authenticate_inbound(
        self,
        *,
        key_id: str,
        presented_key: str,
        audience: str,
    ) -> ApiKeyAuthReceipt:
        key_id = _require_text(key_id, "key_id")
        audience = _require_text(audience, "audience")
        spec = self._inbound.get(key_id)
        if spec is None:
            return self._auth_receipt(
                key_id=key_id,
                audience=audience,
                scopes=(),
                status="DENIED",
                reason="unknown_inbound_key_id",
                public_contract_sha256=_sha256(
                    {"key_id": key_id, "audience": audience, "known": False}
                ),
            )
        if not hmac.compare_digest(spec.audience, audience):
            return self._auth_receipt(
                key_id=spec.key_id,
                audience=audience,
                scopes=(),
                status="DENIED",
                reason="inbound_key_audience_mismatch",
                public_contract_sha256=spec.public_contract_sha256,
            )
        candidate_digest = _secret_sha256(presented_key)
        if not hmac.compare_digest(spec.secret_sha256, candidate_digest):
            return self._auth_receipt(
                key_id=spec.key_id,
                audience=spec.audience,
                scopes=(),
                status="DENIED",
                reason="inbound_key_mismatch",
                public_contract_sha256=spec.public_contract_sha256,
            )
        return self._auth_receipt(
            key_id=spec.key_id,
            audience=spec.audience,
            scopes=spec.scopes,
            status="AUTHENTICATED",
            reason="inbound_key_authenticated",
            public_contract_sha256=spec.public_contract_sha256,
        )

    def lease_outbound(
        self,
        *,
        key_id: str,
        provider: str,
    ) -> OutboundApiKeyLease:
        key_id = _require_text(key_id, "key_id")
        provider = _require_text(provider, "provider")
        spec = self._outbound.get(key_id)
        if spec is None:
            raise ApiKeyContractError("unknown outbound key_id")
        if not hmac.compare_digest(spec.provider, provider):
            raise ApiKeyContractError("outbound key provider mismatch")
        secret = self._environment_getter(spec.environment_variable)
        if secret is None or not secret:
            raise ApiKeyContractError("outbound API key is unavailable")
        receipt = self._lease_receipt(spec)
        return OutboundApiKeyLease(
            key_id=spec.key_id,
            provider=spec.provider,
            header_name=spec.header_name,
            header_prefix=spec.header_prefix,
            scopes=spec.scopes,
            receipt=receipt,
            _secret=secret,
        )

    def _register_unique(self, key_id: str) -> None:
        if key_id in self._inbound or key_id in self._outbound:
            raise ApiKeyContractError("API key_id must be unique across directions")

    @staticmethod
    def _auth_receipt(
        *,
        key_id: str,
        audience: str,
        scopes: tuple[str, ...],
        status: str,
        reason: str,
        public_contract_sha256: str,
    ) -> ApiKeyAuthReceipt:
        payload: dict[str, object] = {
            "schema": API_KEY_AUTH_RECEIPT_SCHEMA_VERSION,
            "receipt_id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        "phios.api-key-auth:"
                        f"{key_id}:{audience}:{status}:{public_contract_sha256}"
                    ),
                )
            ),
            "key_id": key_id,
            "audience": audience,
            "scopes": list(scopes),
            "status": status,
            "reason": reason,
            "public_contract_sha256": public_contract_sha256,
            "credential_exposed": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ApiKeyAuthReceipt(
            schema=API_KEY_AUTH_RECEIPT_SCHEMA_VERSION,
            receipt_id=str(payload["receipt_id"]),
            key_id=key_id,
            audience=audience,
            scopes=scopes,
            status=status,
            reason=reason,
            public_contract_sha256=public_contract_sha256,
            credential_exposed=False,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_sha256(payload),
        )

    @staticmethod
    def _lease_receipt(spec: OutboundApiKeySpec) -> ApiKeyLeaseReceipt:
        payload: dict[str, object] = {
            "schema": API_KEY_LEASE_RECEIPT_SCHEMA_VERSION,
            "receipt_id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        "phios.api-key-lease:"
                        f"{spec.key_id}:{spec.provider}:"
                        f"{spec.public_contract_sha256}"
                    ),
                )
            ),
            "key_id": spec.key_id,
            "provider": spec.provider,
            "scopes": list(spec.scopes),
            "header_name": spec.header_name,
            "status": "LEASED",
            "reason": "outbound_key_resolved_for_provider",
            "public_contract_sha256": spec.public_contract_sha256,
            "secret_source": "environment",
            "credential_exposed": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ApiKeyLeaseReceipt(
            schema=API_KEY_LEASE_RECEIPT_SCHEMA_VERSION,
            receipt_id=str(payload["receipt_id"]),
            key_id=spec.key_id,
            provider=spec.provider,
            scopes=spec.scopes,
            header_name=spec.header_name,
            status="LEASED",
            reason="outbound_key_resolved_for_provider",
            public_contract_sha256=spec.public_contract_sha256,
            secret_source="environment",
            credential_exposed=False,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_sha256(payload),
        )
