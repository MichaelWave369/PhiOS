"""Local operator authority broker for governed Curiosity persistence.

The browser may create and observe a bounded persistence request, but it never
receives an ActionLease, authority key, or accepted verification evidence.

Operator approval happens through a separate local CLI that can read a
0600-protected HMAC key. The broker verifies one exact request proof, constructs
one short-lived AuthorityEpoch and single-use ActionLease, and immediately
executes the existing governed Curiosity persistence path.

This is a local same-user trust boundary, not a defense against malware running
as the same OS account.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import stat
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.core.leased_execution_handoff import LeaseVerificationEvidence
from phios.curiosity_persistence import (
    CURIOSITY_PERSIST_PERMISSION,
    CuriosityPersistPayload,
    CuriosityPersistenceError,
    GovernedCuriosityPersistence,
)
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_BROKER_PORT = 3972
DEFAULT_REQUEST_TTL_SECONDS = 600
LEASE_TTL_SECONDS = 120
MAX_REQUESTS = 32
MAX_REQUEST_BYTES = 131_072
BROKER_ID = "phios.curiosity-authority-broker.local.v0.5"
DEFAULT_PHISHELL_ORIGIN = "http://127.0.0.1:3969"

_BROKER_POLICY = {
    "schema_version": "phios.curiosity_authority_policy.v0.5",
    "broker_id": BROKER_ID,
    "capability_id": "curiosity.persist",
    "permission": CURIOSITY_PERSIST_PERMISSION,
    "effects": ["filesystem.change"],
    "approval_mode": "local_cli_hmac_exact_payload",
    "lease_max_uses": 1,
}
_ENFORCEMENT_EVIDENCE = hashlib.sha256(
    b"curiosity.persist writes only through bounded CuriosityStore append"
).hexdigest()


class CuriosityAuthorityBrokerError(ValueError):
    """Raised when a broker request or approval cannot be trusted safely."""


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
        raise CuriosityAuthorityBrokerError(
            "broker payload must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CuriosityAuthorityBrokerError(
            f"{field} must be a non-empty ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CuriosityAuthorityBrokerError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CuriosityAuthorityBrokerError(
            f"{field} must include a timezone offset"
        )
    return parsed.astimezone(UTC)


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise CuriosityAuthorityBrokerError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise CuriosityAuthorityBrokerError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise CuriosityAuthorityBrokerError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if len(text) != 64 or any(
        char not in "0123456789abcdef"
        for char in text
    ):
        raise CuriosityAuthorityBrokerError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def default_state_root() -> Path:
    configured = os.environ.get("PHIOS_STATE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".phios"


def default_key_path() -> Path:
    configured = os.environ.get("PHIOS_CURIOSITY_BROKER_KEY")
    if configured:
        return Path(configured).expanduser()
    return default_state_root() / "authority" / "curiosity-broker.key"


def default_principal_id() -> str:
    return os.environ.get(
        "PHIOS_OPERATOR_PRINCIPAL",
        "operator:local",
    )


def default_port() -> int:
    raw = os.environ.get("PHIOS_CURIOSITY_BROKER_PORT")
    if raw is None:
        return DEFAULT_BROKER_PORT
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise CuriosityAuthorityBrokerError(
            "PHIOS_CURIOSITY_BROKER_PORT must be from 1024 to 65535"
        )
    return port


def load_or_create_local_key(path: Path) -> bytes:
    resolved = path.expanduser()
    resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        fd = os.open(
            resolved,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        pass
    else:
        try:
            secret = secrets.token_bytes(32).hex().encode("ascii")
            os.write(fd, secret + b"\n")
        finally:
            os.close(fd)

    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise CuriosityAuthorityBrokerError(
            "broker key permissions must not grant group/other access"
        )

    raw = resolved.read_text(encoding="ascii").strip()
    if len(raw) != 64 or any(
        char not in "0123456789abcdef"
        for char in raw
    ):
        raise CuriosityAuthorityBrokerError(
            "broker key must contain 32 random bytes as lowercase hex"
        )
    return bytes.fromhex(raw)


@dataclass(frozen=True, slots=True)
class OperatorApproval:
    request_id: str
    payload_sha256: str
    principal_id: str
    approved_at: str
    broker_id: str
    proof_hmac_sha256: str

    def body_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "payload_sha256": self.payload_sha256,
            "principal_id": self.principal_id,
            "approved_at": self.approved_at,
            "broker_id": self.broker_id,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["proof_hmac_sha256"] = self.proof_hmac_sha256
        return payload


def create_operator_approval(
    *,
    request_id: str,
    payload_sha256: str,
    principal_id: str,
    approved_at: str,
    key: bytes,
) -> OperatorApproval:
    body = {
        "request_id": _require_text(
            request_id,
            "request_id",
            maximum=96,
        ),
        "payload_sha256": _require_sha256(
            payload_sha256,
            "payload_sha256",
        ),
        "principal_id": _require_text(
            principal_id,
            "principal_id",
            maximum=256,
        ),
        "approved_at": _parse_time(
            approved_at,
            "approved_at",
        ).isoformat(),
        "broker_id": BROKER_ID,
    }
    proof = hmac.new(
        key,
        _canonical_json(body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return OperatorApproval(
        request_id=str(body["request_id"]),
        payload_sha256=str(body["payload_sha256"]),
        principal_id=str(body["principal_id"]),
        approved_at=str(body["approved_at"]),
        broker_id=BROKER_ID,
        proof_hmac_sha256=proof,
    )


def verify_operator_approval(
    approval: OperatorApproval,
    *,
    key: bytes,
) -> bool:
    expected = hmac.new(
        key,
        _canonical_json(approval.body_dict()).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(
        expected,
        approval.proof_hmac_sha256,
    )


@dataclass(slots=True)
class PersistRequest:
    request_id: str
    payload: CuriosityPersistPayload
    payload_sha256: str
    requested_at: str
    expires_at: str
    status: str = "pending"
    reason: str = "awaiting_operator_approval"
    approved_at: str | None = None
    artifact_sha256: str | None = None
    execution_receipt: dict[str, object] | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": "phios.curiosity-persist-request.v0.5",
            "requestId": self.request_id,
            "payload": self.payload.to_dict(),
            "payloadSha256": self.payload_sha256,
            "requestedAt": self.requested_at,
            "expiresAt": self.expires_at,
            "status": self.status,
            "reason": self.reason,
            "approvedAt": self.approved_at,
            "artifactSha256": self.artifact_sha256,
            "executionReceipt": self.execution_receipt,
            "approvalCommand": (
                "python -m phios.curiosity_authority_broker "
                f"approve {self.request_id}"
            ),
            "operationalAuthority": False,
            "actionAuthority": False,
            "executionAuthority": False,
            "effectPerformed": self.status == "succeeded",
        }


class CuriosityAuthorityBroker:
    """Bounded local request broker plus operator-approved execution."""

    def __init__(
        self,
        *,
        state_root: Path,
        principal_id: str,
        key_path: Path,
        request_ttl_seconds: int = DEFAULT_REQUEST_TTL_SECONDS,
    ) -> None:
        if not isinstance(request_ttl_seconds, int) or not (
            60 <= request_ttl_seconds <= 3600
        ):
            raise CuriosityAuthorityBrokerError(
                "request_ttl_seconds must be from 60 to 3600"
            )
        self.state_root = state_root.expanduser()
        self.principal_id = _require_text(
            principal_id,
            "principal_id",
            maximum=256,
        )
        self.key_path = key_path.expanduser()
        self.key = load_or_create_local_key(self.key_path)
        self.request_ttl_seconds = request_ttl_seconds
        self.policy_sha256 = _sha256(_BROKER_POLICY)
        self._requests: dict[str, PersistRequest] = {}
        self._lock = threading.RLock()
        self._service = GovernedCuriosityPersistence(
            state_root=self.state_root,
            allowed_permissions=(CURIOSITY_PERSIST_PERMISSION,),
        )

    def health(self) -> dict[str, object]:
        return {
            "schemaVersion": "phios.curiosity-authority-broker.v0.5",
            "brokerId": BROKER_ID,
            "localOnly": True,
            "principalId": self.principal_id,
            "capabilityId": self._service.capability.id,
            "permission": CURIOSITY_PERSIST_PERMISSION,
            "approvalMode": "local_cli_hmac_exact_payload",
            "browserCanApprove": False,
            "browserReceivesLease": False,
            "status": "ready",
            "operationalAuthority": False,
            "actionAuthority": False,
            "executionAuthority": False,
            "effectPerformed": False,
        }

    def create_request(
        self,
        browser_payload: Mapping[str, Any],
    ) -> PersistRequest:
        expected = {
            "artifact_kind",
            "title",
            "content",
            "created_at",
            "tags",
            "evidence_ref_sha256s",
            "parent_artifact_sha256s",
        }
        data = dict(browser_payload)
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise CuriosityAuthorityBrokerError(
                "browser Curiosity request fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        canonical = CuriosityPersistPayload.from_mapping(
            {
                "schema_version": (
                    "phios.curiosity_persist_payload.v0.4"
                ),
                "artifact_kind": data["artifact_kind"],
                "title": data["title"],
                "content": data["content"],
                "created_at": data["created_at"],
                "created_by": self.principal_id,
                "tags": data["tags"],
                "evidence_ref_sha256s": (
                    data["evidence_ref_sha256s"]
                ),
                "parent_artifact_sha256s": (
                    data["parent_artifact_sha256s"]
                ),
            }
        )
        payload_dict = canonical.to_dict()
        payload_sha = GovernedActionBinder().payload_sha256(
            payload_dict
        )
        now = datetime.now(UTC)
        request_id = (
            "curiosity-request-" + secrets.token_hex(16)
        )
        item = PersistRequest(
            request_id=request_id,
            payload=canonical,
            payload_sha256=payload_sha,
            requested_at=now.isoformat(),
            expires_at=(
                now + timedelta(seconds=self.request_ttl_seconds)
            ).isoformat(),
        )
        with self._lock:
            self._expire_locked(now)
            if len(self._requests) >= MAX_REQUESTS:
                oldest = min(
                    self._requests.values(),
                    key=lambda row: row.requested_at,
                )
                if oldest.status == "pending":
                    raise CuriosityAuthorityBrokerError(
                        "broker request capacity reached"
                    )
                del self._requests[oldest.request_id]
            self._requests[request_id] = item
        return item

    def get_request(
        self,
        request_id: str,
    ) -> PersistRequest | None:
        with self._lock:
            self._expire_locked(datetime.now(UTC))
            return self._requests.get(request_id)

    def approve(
        self,
        approval: OperatorApproval,
    ) -> PersistRequest:
        if not verify_operator_approval(
            approval,
            key=self.key,
        ):
            raise CuriosityAuthorityBrokerError(
                "operator approval HMAC verification failed"
            )
        if approval.broker_id != BROKER_ID:
            raise CuriosityAuthorityBrokerError(
                "operator approval broker_id mismatch"
            )

        now = datetime.now(UTC)
        approved = _parse_time(
            approval.approved_at,
            "approved_at",
        )
        if approved > now + timedelta(seconds=5):
            raise CuriosityAuthorityBrokerError(
                "operator approval timestamp is in the future"
            )
        if now - approved > timedelta(seconds=90):
            raise CuriosityAuthorityBrokerError(
                "operator approval proof is stale"
            )

        with self._lock:
            self._expire_locked(now)
            item = self._requests.get(approval.request_id)
            if item is None:
                raise CuriosityAuthorityBrokerError(
                    "unknown persistence request"
                )
            if item.status != "pending":
                raise CuriosityAuthorityBrokerError(
                    "persistence request is not pending"
                )
            if approval.payload_sha256 != item.payload_sha256:
                raise CuriosityAuthorityBrokerError(
                    "operator approval payload digest mismatch"
                )
            if approval.principal_id != self.principal_id:
                raise CuriosityAuthorityBrokerError(
                    "operator approval principal mismatch"
                )
            if now >= _parse_time(item.expires_at, "expires_at"):
                item.status = "expired"
                item.reason = "request_expired"
                raise CuriosityAuthorityBrokerError(
                    "persistence request expired"
                )

            item.status = "approved"
            item.reason = "operator_approval_verified"
            item.approved_at = approval.approved_at

        try:
            receipt, artifact_sha = self._execute(
                item=item,
                approval=approval,
            )
        except Exception:
            with self._lock:
                item.status = "failed"
                item.reason = "broker_execution_failed"
            raise

        with self._lock:
            item.execution_receipt = receipt
            item.artifact_sha256 = artifact_sha
            status = str(receipt.get("status", ""))
            if status == "SUCCEEDED":
                item.status = "succeeded"
                item.reason = "curiosity_persisted"
            else:
                item.status = "held"
                item.reason = str(
                    receipt.get(
                        "reason",
                        "governed_execution_not_succeeded",
                    )
                )
            return item

    def _execute(
        self,
        *,
        item: PersistRequest,
        approval: OperatorApproval,
    ) -> tuple[dict[str, object], str]:
        payload_dict = item.payload.to_dict()
        plan = self._plan(item)
        binder = GovernedActionBinder()
        grant = ActionBindingGrant(
            grant_id=f"grant:{item.request_id}",
            authority_source="local-operator-hmac-approval",
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            transition_index=0,
            source_state_id="CURIOUS",
            target_state_id="PERSISTED",
            capability_id=self._service.capability.id,
            payload_sha256=item.payload_sha256,
        )
        binding, binding_receipt = binder.bind(
            plan=plan,
            transition_index=0,
            capability=self._service.capability,
            payload=payload_dict,
            grant=grant,
        )
        if binding is None or binding_receipt.status != "BOUND":
            raise CuriosityAuthorityBrokerError(
                "Curiosity persistence binding was not admitted"
            )

        authorization_receipt_sha256 = _sha256(
            {
                "schema_version": (
                    "phios.curiosity_authorization_receipt.v0.5"
                ),
                "approval": approval.to_dict(),
                "payload_sha256": item.payload_sha256,
                "capability_id": self._service.capability.id,
                "permission": CURIOSITY_PERSIST_PERMISSION,
            }
        )

        approved_at = _parse_time(
            approval.approved_at,
            "approved_at",
        )
        lease_expires = approved_at + timedelta(
            seconds=LEASE_TTL_SECONDS
        )
        epoch = AuthorityEpoch.build(
            principal_id=self.principal_id,
            policy_sha256=self.policy_sha256,
            ceiling=(CURIOSITY_PERSIST_PERMISSION,),
            events=(
                AuthoritativeAuthorityEvent(
                    event_id=f"approval:{item.request_id}",
                    sequence=1,
                    kind=AuthorityEventKind.GRANT,
                    permission=CURIOSITY_PERSIST_PERMISSION,
                    authority_source=(
                        "local-operator-hmac-approval"
                    ),
                    effective_at=approved_at.isoformat(),
                    expires_at=lease_expires.isoformat(),
                ),
            ),
            observed_at=approved_at.isoformat(),
        )

        intent = EffectIntent.build(
            capability_id=binding.capability_id,
            capability_version=binding.capability_version,
            payload_sha256=binding.payload_sha256,
            declared_at=approved_at.isoformat(),
            effects_declared=binding.effects_declared,
        )
        rule = EnforcementRule.build(
            rule_id="curiosity-store-append-boundary",
            effect_scope=("filesystem.change",),
            constraint=(
                "curiosity.persist may append only through "
                "the configured CuriosityStore"
            ),
            layer="linux_permissions",
            boundary="kernel_boundary",
            status="enforced",
            mechanism=(
                "bounded CuriosityStore append-only executor"
            ),
            evidence_ref_sha256s=(
                _ENFORCEMENT_EVIDENCE,
            ),
        )
        enforcement = EnforcementProfile.build(
            intent=intent,
            rules=(rule,),
        )
        lease = ActionLease.issue(
            principal_id=self.principal_id,
            issuer_id=BROKER_ID,
            authorization_receipt_sha256=(
                authorization_receipt_sha256
            ),
            intent=intent,
            enforcement=enforcement,
            authority_epoch=epoch,
            permissions_authorized=(
                binding.permissions_requested
            ),
            accepted_unenforced_effects=(),
            issued_at=approved_at.isoformat(),
            valid_from=approved_at.isoformat(),
            valid_until=lease_expires.isoformat(),
        )

        verification_receipt_sha256 = _sha256(
            {
                "schema_version": (
                    "phios.curiosity_lease_verification.v0.5"
                ),
                "broker_id": BROKER_ID,
                "lease_sha256": lease.action_lease_sha256,
                "authorization_receipt_sha256": (
                    authorization_receipt_sha256
                ),
                "approval_hmac_sha256": (
                    approval.proof_hmac_sha256
                ),
                "verified": True,
            }
        )
        verification = LeaseVerificationEvidence(
            lease_sha256=lease.action_lease_sha256,
            issuer_id=BROKER_ID,
            authorization_receipt_sha256=(
                authorization_receipt_sha256
            ),
            verifier_id=(
                "phios.curiosity-authority-broker.hmac-verifier"
            ),
            verification_receipt_sha256=(
                verification_receipt_sha256
            ),
            accepted=True,
        )

        receipt = self._service.execute(
            plan=plan,
            binding=binding,
            payload=payload_dict,
            lease=lease,
            verification=verification,
            current_authority_epoch_sha256=(
                epoch.authority_epoch_sha256
            ),
            checked_at=datetime.now(UTC).isoformat(),
        )
        artifact_sha = (
            item.payload.to_artifact().curiosity_artifact_sha256
        )
        return receipt.to_dict(), artifact_sha

    def _plan(
        self,
        item: PersistRequest,
    ):
        route_body = {
            "schema": "phios.field_aware_route_receipt.v0.4",
            "status": "found",
            "field_law_sha256": self.policy_sha256,
            "field_state_sha256": item.payload_sha256,
            "field_revision": 0,
            "bindings": [],
            "path_receipt_sha256": _sha256(
                {
                    "request_id": item.request_id,
                    "path": ["CURIOUS", "PERSISTED"],
                }
            ),
            "path_ids": ["CURIOUS", "PERSISTED"],
            "total_cost": 1.0,
            "optimality_scope": (
                "single_explicit_operator_approved_persistence_path"
            ),
            "action_authority": False,
        }
        route_digest = _sha256(route_body)
        route = FieldAwareRouteReceipt(
            schema=str(route_body["schema"]),
            status=str(route_body["status"]),
            field_law_sha256=str(
                route_body["field_law_sha256"]
            ),
            field_state_sha256=str(
                route_body["field_state_sha256"]
            ),
            field_revision=0,
            bindings=(),
            path_receipt_sha256=str(
                route_body["path_receipt_sha256"]
            ),
            path_ids=("CURIOUS", "PERSISTED"),
            total_cost=1.0,
            optimality_scope=str(
                route_body["optimality_scope"]
            ),
            action_authority=False,
            receipt_sha256=route_digest,
        )
        return GovernedPlanAdoptionGate().initialize_plan(
            plan_id=f"plan:{item.request_id}",
            route_receipt=route,
        )

    def _expire_locked(
        self,
        now: datetime,
    ) -> None:
        for item in self._requests.values():
            if (
                item.status == "pending"
                and now >= _parse_time(
                    item.expires_at,
                    "expires_at",
                )
            ):
                item.status = "expired"
                item.reason = "request_expired"


class CuriosityAuthorityHandler(BaseHTTPRequestHandler):
    server: "CuriosityAuthorityServer"

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        return

    def _json(
        self,
        status: HTTPStatus,
        body: dict[str, object],
        *,
        browser_visible: bool = False,
    ) -> None:
        encoded = _canonical_json(body).encode("utf-8")
        self.send_response(status.value)
        self.send_header(
            "content-type",
            "application/json; charset=utf-8",
        )
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header(
            "cross-origin-resource-policy",
            "same-site" if browser_visible else "same-origin",
        )
        self.send_header("referrer-policy", "no-referrer")
        if browser_visible:
            origin = self.headers.get("origin")
            if origin == DEFAULT_PHISHELL_ORIGIN:
                self.send_header("access-control-allow-origin", origin)
                self.send_header("vary", "Origin")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict[str, object]:
        content_type = self.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise CuriosityAuthorityBrokerError(
                "content-type must be application/json"
            )
        raw_length = self.headers.get("content-length")
        if raw_length is None:
            raise CuriosityAuthorityBrokerError(
                "content-length is required"
            )
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise CuriosityAuthorityBrokerError(
                "content-length must be an integer"
            ) from exc
        if length < 2 or length > MAX_REQUEST_BYTES:
            raise CuriosityAuthorityBrokerError(
                "request body exceeds broker bounds"
            )
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CuriosityAuthorityBrokerError(
                "request body must be valid JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise CuriosityAuthorityBrokerError(
                "request body must be a JSON object"
            )
        return parsed

    def do_OPTIONS(self) -> None:
        parsed = urlsplit(self.path)
        origin = self.headers.get("origin")
        requested_method = self.headers.get(
            "access-control-request-method"
        )
        if (
            parsed.path
            == "/api/v1/curiosity/persist-requests"
            and origin == DEFAULT_PHISHELL_ORIGIN
            and requested_method == "POST"
        ):
            self.send_response(HTTPStatus.NO_CONTENT.value)
            self.send_header("access-control-allow-origin", origin)
            self.send_header("access-control-allow-methods", "POST")
            self.send_header(
                "access-control-allow-headers",
                "content-type, accept",
            )
            self.send_header("access-control-max-age", "600")
            self.send_header("vary", "Origin")
            self.end_headers()
            return
        self.send_response(HTTPStatus.FORBIDDEN.value)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.query:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "query_not_supported"},
            )
            return

        if parsed.path == "/api/v1/health":
            self._json(
                HTTPStatus.OK,
                self.server.broker.health(),
                browser_visible=True,
            )
            return

        prefix = "/api/v1/curiosity/persist-requests/"
        if parsed.path.startswith(prefix):
            request_id = parsed.path[len(prefix):]
            if (
                not request_id
                or "/" in request_id
                or len(request_id) > 96
            ):
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request_id"},
                )
                return
            item = self.server.broker.get_request(
                request_id
            )
            if item is None:
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "request_not_found"},
                )
                return
            self._json(
                HTTPStatus.OK,
                item.public_dict(),
                browser_visible=True,
            )
            return

        self._json(
            HTTPStatus.NOT_FOUND,
            {"error": "not_found"},
        )

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.query:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "query_not_supported"},
            )
            return
        try:
            body = self._read_json()

            if (
                parsed.path
                == "/api/v1/curiosity/persist-requests"
            ):
                item = self.server.broker.create_request(
                    body
                )
                self._json(
                    HTTPStatus.CREATED,
                    item.public_dict(),
                    browser_visible=True,
                )
                return

            if (
                parsed.path
                == "/api/v1/operator-approval"
            ):
                expected = {
                    "request_id",
                    "payload_sha256",
                    "principal_id",
                    "approved_at",
                    "broker_id",
                    "proof_hmac_sha256",
                }
                if set(body) != expected:
                    raise CuriosityAuthorityBrokerError(
                        "operator approval fields mismatch"
                    )
                approval = OperatorApproval(
                    request_id=_require_text(
                        body["request_id"],
                        "request_id",
                        maximum=96,
                    ),
                    payload_sha256=_require_sha256(
                        body["payload_sha256"],
                        "payload_sha256",
                    ),
                    principal_id=_require_text(
                        body["principal_id"],
                        "principal_id",
                        maximum=256,
                    ),
                    approved_at=_parse_time(
                        body["approved_at"],
                        "approved_at",
                    ).isoformat(),
                    broker_id=_require_text(
                        body["broker_id"],
                        "broker_id",
                        maximum=128,
                    ),
                    proof_hmac_sha256=_require_sha256(
                        body["proof_hmac_sha256"],
                        "proof_hmac_sha256",
                    ),
                )
                item = self.server.broker.approve(
                    approval
                )
                self._json(
                    HTTPStatus.OK,
                    item.public_dict(),
                )
                return

            self._json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
            )
        except (
            CuriosityAuthorityBrokerError,
            CuriosityPersistenceError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "broker_request_rejected",
                    "reason": str(exc),
                    "operationalAuthority": False,
                    "actionAuthority": False,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
                browser_visible=(
                    parsed.path
                    == "/api/v1/curiosity/persist-requests"
                ),
            )


class CuriosityAuthorityServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        broker: CuriosityAuthorityBroker,
    ) -> None:
        if address[0] != LOOPBACK_HOST:
            raise CuriosityAuthorityBrokerError(
                "authority broker must bind IPv4 loopback"
            )
        self.broker = broker
        super().__init__(
            address,
            CuriosityAuthorityHandler,
        )


def _http_json(
    *,
    method: str,
    url: str,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    encoded = (
        _canonical_json(body).encode("utf-8")
        if body is not None
        else None
    )
    headers = {"accept": "application/json"}
    if encoded is not None:
        headers["content-type"] = "application/json"
    request = urllib_request.Request(
        url,
        data=encoded,
        headers=headers,
        method=method,
    )
    try:
        with urllib_request.urlopen(
            request,
            timeout=3,
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except (
        urllib_error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        raise CuriosityAuthorityBrokerError(
            f"broker request failed: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CuriosityAuthorityBrokerError(
            "broker response must be an object"
        )
    return payload


def approve_request_cli(
    *,
    request_id: str,
    port: int,
    key_path: Path,
    assume_yes: bool,
) -> dict[str, object]:
    base = f"http://{LOOPBACK_HOST}:{port}"
    item = _http_json(
        method="GET",
        url=(
            f"{base}/api/v1/curiosity/"
            f"persist-requests/{request_id}"
        ),
    )
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise CuriosityAuthorityBrokerError(
            "broker request has no valid payload"
        )

    print("Curiosity persistence request")
    print(f"  request: {item.get('requestId')}")
    print(f"  digest:  {item.get('payloadSha256')}")
    print(f"  kind:    {payload.get('artifact_kind')}")
    print(f"  title:   {payload.get('title')}")
    print(f"  creator: {payload.get('created_by')}")
    print()
    print("This approval authorizes one exact local filesystem append.")

    if not assume_yes:
        answer = input(
            'Type "approve" to authorize this exact payload: '
        ).strip()
        if answer != "approve":
            raise CuriosityAuthorityBrokerError(
                "operator did not approve request"
            )

    key = load_or_create_local_key(key_path)
    approval = create_operator_approval(
        request_id=_require_text(
            item.get("requestId"),
            "requestId",
            maximum=96,
        ),
        payload_sha256=_require_sha256(
            item.get("payloadSha256"),
            "payloadSha256",
        ),
        principal_id=_require_text(
            payload.get("created_by"),
            "created_by",
            maximum=256,
        ),
        approved_at=_canonical_now(),
        key=key,
    )
    return _http_json(
        method="POST",
        url=f"{base}/api/v1/operator-approval",
        body=approval.to_dict(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "PhiOS local Curiosity authority broker"
        )
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    serve = sub.add_parser("serve")
    serve.add_argument(
        "--port",
        type=int,
        default=default_port(),
    )
    serve.add_argument(
        "--state-root",
        type=Path,
        default=default_state_root(),
    )
    serve.add_argument(
        "--principal",
        default=default_principal_id(),
    )
    serve.add_argument(
        "--key-path",
        type=Path,
        default=default_key_path(),
    )

    approve = sub.add_parser("approve")
    approve.add_argument("request_id")
    approve.add_argument(
        "--port",
        type=int,
        default=default_port(),
    )
    approve.add_argument(
        "--key-path",
        type=Path,
        default=default_key_path(),
    )
    approve.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Skip interactive confirmation. Intended for "
            "automation/tests, not normal operator use."
        ),
    )

    args = parser.parse_args()
    if args.command == "approve":
        result = approve_request_cli(
            request_id=args.request_id,
            port=args.port,
            key_path=args.key_path,
            assume_yes=args.yes,
        )
        print(_canonical_json(result))
        return

    if not 1024 <= args.port <= 65535:
        raise SystemExit("port must be from 1024 to 65535")

    broker = CuriosityAuthorityBroker(
        state_root=args.state_root,
        principal_id=args.principal,
        key_path=args.key_path,
    )
    server = CuriosityAuthorityServer(
        (LOOPBACK_HOST, args.port),
        broker,
    )
    print(
        "PhiOS Curiosity authority broker: "
        f"http://{LOOPBACK_HOST}:{args.port}"
    )
    print(
        "Operator approval remains outside the browser. "
        "Use the approve subcommand for exact requests."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
