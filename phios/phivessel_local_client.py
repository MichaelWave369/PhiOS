"""Reference local client for the PhiVessel ↔ PhiOS v0.38 handshake.

This is a transport client, not an authority broker. It keeps the ephemeral
session token in memory and exposes only observe, propose, and execute(leaseId).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPResponse
from typing import Mapping
from urllib.parse import urlencode

from phios.phivessel_bridge import (
    PHIVESSEL_BRIDGE_VERSION,
    PhiVesselObservationKind,
    PhiVesselProposalType,
)
from phios.phivessel_handshake import PhiVesselSessionOperation

LOOPBACK_HOST = "127.0.0.1"
SESSION_ID_HEADER = "X-PhiVessel-Session-Id"
SESSION_TOKEN_HEADER = "X-PhiVessel-Session-Token"


class PhiVesselLocalClientError(ValueError):
    """Raised when the local bridge response cannot be trusted."""


@dataclass(frozen=True, slots=True)
class PhiVesselLocalSession:
    session_id: str
    session_token: str
    server_instance_id: str
    selected_bridge_version: str
    granted_operations: tuple[PhiVesselSessionOperation, ...]
    expires_at: str
    client_identity_authenticated: bool = False
    action_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.session_id.startswith("pvs:"):
            raise PhiVesselLocalClientError("session_id is malformed")
        if len(self.session_token) != 64:
            raise PhiVesselLocalClientError("session_token is malformed")
        if not self.server_instance_id.startswith("pvh:"):
            raise PhiVesselLocalClientError(
                "server_instance_id is malformed"
            )
        if self.client_identity_authenticated is not False:
            raise PhiVesselLocalClientError(
                "v0.38 cannot claim authenticated client identity"
            )
        if self.action_authority or self.execution_authority:
            raise PhiVesselLocalClientError(
                "local transport session cannot carry action authority"
            )


class PhiVesselLocalClient:
    """Loopback-only reference client for native/local Vessie integration."""

    def __init__(
        self,
        *,
        port: int = 3973,
        client_instance_id: str = "super-phivessel:desktop:local",
        timeout_seconds: float = 2.5,
    ) -> None:
        if not isinstance(port, int) or isinstance(port, bool):
            raise PhiVesselLocalClientError("port must be an integer")
        if port < 1 or port > 65535:
            raise PhiVesselLocalClientError("port is outside TCP range")
        if not client_instance_id or len(client_instance_id) > 256:
            raise PhiVesselLocalClientError(
                "client_instance_id is invalid"
            )
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise PhiVesselLocalClientError(
                "timeout_seconds must be within 0-30"
            )
        self.port = port
        self.client_instance_id = client_instance_id
        self.timeout_seconds = timeout_seconds
        self.session: PhiVesselLocalSession | None = None

    def handshake(
        self,
        *,
        client_nonce: str,
        requested_operations: tuple[PhiVesselSessionOperation, ...],
        supported_bridge_versions: tuple[str, ...] = (
            PHIVESSEL_BRIDGE_VERSION,
        ),
    ) -> PhiVesselLocalSession:
        payload = {
            "clientInstanceId": self.client_instance_id,
            "clientNonce": client_nonce,
            "supportedBridgeVersions": list(
                supported_bridge_versions
            ),
            "requestedOperations": [
                item.value for item in requested_operations
            ],
        }
        response = self._json_request(
            "POST",
            "/api/v1/phivessel/handshake",
            payload=payload,
            include_session=False,
        )
        handshake = response.get("handshake")
        if not isinstance(handshake, Mapping):
            raise PhiVesselLocalClientError(
                "handshake response is missing"
            )
        if (
            response.get("transportSchemaVersion")
            != "phios.phivessel-handshake-transport.v0.38"
            or response.get("transport") != "loopback-http"
            or response.get("localOnly") is not True
        ):
            raise PhiVesselLocalClientError(
                "host returned an unsupported handshake transport"
            )
        if response.get("clientIdentityAuthenticated") is not False:
            raise PhiVesselLocalClientError(
                "host claimed unsupported client authentication"
            )
        if response.get("transportSessionOnly") is not True:
            raise PhiVesselLocalClientError(
                "host did not preserve transport-only semantics"
            )
        if (
            response.get("actionLeaseStillRequiredForExecution")
            is not True
        ):
            raise PhiVesselLocalClientError(
                "host did not preserve ActionLease requirement"
            )
        if (
            handshake.get("client_instance_id") != self.client_instance_id
            or handshake.get("client_nonce") != client_nonce
        ):
            raise PhiVesselLocalClientError(
                "host handshake did not bind the requested client instance"
            )
        selected = handshake.get("selected_bridge_version")
        if selected not in set(supported_bridge_versions):
            raise PhiVesselLocalClientError(
                "host selected an unoffered bridge version"
            )
        raw_operations = handshake.get("granted_operations")
        if not isinstance(raw_operations, list):
            raise PhiVesselLocalClientError(
                "granted_operations is invalid"
            )
        try:
            operations = tuple(
                PhiVesselSessionOperation(item)
                for item in raw_operations
            )
        except (TypeError, ValueError) as exc:
            raise PhiVesselLocalClientError(
                "granted operation is unsupported"
            ) from exc
        session = PhiVesselLocalSession(
            session_id=_text(handshake.get("session_id"), "session_id"),
            session_token=_text(
                handshake.get("session_token"),
                "session_token",
            ),
            server_instance_id=_text(
                handshake.get("server_instance_id"),
                "server_instance_id",
            ),
            selected_bridge_version=_text(
                handshake.get("selected_bridge_version"),
                "selected_bridge_version",
            ),
            granted_operations=operations,
            expires_at=_text(
                handshake.get("expires_at"),
                "expires_at",
            ),
            client_identity_authenticated=False,
        )
        self.session = session
        return session

    def observe(
        self,
        *,
        kind: PhiVesselObservationKind,
        lease_id: str | None = None,
    ) -> Mapping[str, object]:
        query: dict[str, str] = {"kind": kind.value}
        if lease_id is not None:
            query["leaseId"] = lease_id
        self._require_operation(PhiVesselSessionOperation.OBSERVE)
        return self._json_request(
            "GET",
            "/api/v1/phivessel/observe?" + urlencode(query),
        )

    def propose(
        self,
        *,
        work_id: str,
        packet_refs: tuple[str, ...],
        proposal_type: PhiVesselProposalType,
    ) -> Mapping[str, object]:
        self._require_operation(PhiVesselSessionOperation.PROPOSE)
        return self._json_request(
            "POST",
            "/api/v1/phivessel/proposals",
            payload={
                "workId": work_id,
                "packetRefs": list(packet_refs),
                "proposalType": proposal_type.value,
            },
        )

    def execute(
        self,
        *,
        lease_id: str,
    ) -> Mapping[str, object]:
        self._require_operation(PhiVesselSessionOperation.EXECUTE)
        return self._json_request(
            "POST",
            "/api/v1/phivessel/execute",
            payload={"leaseId": lease_id},
        )

    def _require_operation(
        self,
        operation: PhiVesselSessionOperation,
    ) -> None:
        session = self.session
        if session is None:
            raise PhiVesselLocalClientError(
                "handshake is required before bridge calls"
            )
        if operation not in set(session.granted_operations):
            raise PhiVesselLocalClientError(
                f"{operation.value} was not granted by the host handshake"
            )

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        include_session: bool = True,
    ) -> Mapping[str, object]:
        headers = {"accept": "application/json"}
        if include_session:
            session = self.session
            if session is None:
                raise PhiVesselLocalClientError(
                    "handshake is required before bridge calls"
                )
            headers[SESSION_ID_HEADER] = session.session_id
            headers[SESSION_TOKEN_HEADER] = session.session_token

        encoded: bytes | None = None
        if payload is not None:
            encoded = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"
            headers["content-length"] = str(len(encoded))

        connection = HTTPConnection(
            LOOPBACK_HOST,
            self.port,
            timeout=self.timeout_seconds,
        )
        try:
            connection.request(
                method,
                path,
                body=encoded,
                headers=headers,
            )
            response = connection.getresponse()
            return self._read_response(response)
        finally:
            connection.close()

    @staticmethod
    def _read_response(
        response: HTTPResponse,
    ) -> Mapping[str, object]:
        try:
            value = json.loads(response.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhiVesselLocalClientError(
                "local bridge returned invalid JSON"
            ) from exc
        if not isinstance(value, Mapping):
            raise PhiVesselLocalClientError(
                "local bridge response must be an object"
            )
        if response.status < 200 or response.status >= 300:
            error = value.get("error")
            raise PhiVesselLocalClientError(
                str(error or f"bridge HTTP {response.status}")
            )
        return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PhiVesselLocalClientError(f"{field} is invalid")
    return value


__all__ = [
    "PhiVesselLocalClient",
    "PhiVesselLocalClientError",
    "PhiVesselLocalSession",
]
