from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from phios.macro_authority_request import (
    GhostWalkAuthorityRequest,
    GhostWalkAuthorityRequestReadiness,
    GhostWalkAuthorityRequestReadinessReason,
    GhostWalkAuthorityRequestState,
    GhostWalkRequestScopeKind,
    GhostWalkRequestedAuthorityKind,
)
from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)

TARGET = "a" * 64
ADMISSION = "b" * 64
INTENT = "c" * 64
PROFILE = "d" * 64


class FakeSurface:
    def snapshot(self) -> object:
        raise AssertionError("status endpoint not used")


class FakeAuthorityRequests:
    def __init__(self) -> None:
        self.created: GhostWalkAuthorityRequest | None = None
        self.calls: list[dict[str, str]] = []

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorityRequestReadiness:
        assert target_inference_receipt_sha256 == TARGET
        return GhostWalkAuthorityRequestReadiness(
            target_inference_receipt_sha256=TARGET,
            accepted_intent_revision_sha256=INTENT,
            policy_profile_sha256=PROFILE,
            policy_decision="ALLOW_REQUEST",
            ready=self.created is None,
            reason=(
                GhostWalkAuthorityRequestReadinessReason.READY
                if self.created is None
                else GhostWalkAuthorityRequestReadinessReason
                .REQUEST_ALREADY_EXISTS
            ),
            admission_receipt_sha256=ADMISSION,
            existing_authority_request_sha256=(
                None
                if self.created is None
                else self.created.authority_request_sha256
            ),
        )

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorityRequest | None:
        assert target_inference_receipt_sha256 == TARGET
        return self.created

    def create(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_admission_receipt_sha256: str,
        requested_at: str | None = None,
    ) -> GhostWalkAuthorityRequest:
        self.calls.append(
            {
                "target": target_inference_receipt_sha256,
                "admission": expected_admission_receipt_sha256,
            }
        )
        self.created = GhostWalkAuthorityRequest(
            admission_receipt_sha256=ADMISSION,
            target_inference_receipt_sha256=TARGET,
            accepted_intent_revision_sha256=INTENT,
            policy_profile_sha256=PROFILE,
            intent_family="OPEN",
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            requester_id="operator:local",
            requested_authority_kind=(
                GhostWalkRequestedAuthorityKind.ACTION_AUTHORITY
            ),
            requested_scope_kind=(
                GhostWalkRequestScopeKind.ACCEPTED_INTENT
            ),
            requested_scope_value=(
                "OPEN_NETWORK_ADAPTER_PROPERTIES"
            ),
            request_state=(
                GhostWalkAuthorityRequestState.PENDING_AUTHORIZATION
            ),
            requested_at="2026-09-27T07:30:00+00:00",
        )
        return self.created


def _server(
    service: FakeAuthorityRequests,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=FakeSurface(),  # type: ignore[arg-type]
        authority_requests=service,  # type: ignore[arg-type]
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    return server, thread


def _request(
    server: GhostWalkControlServer,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(
        LOOPBACK_HOST,
        server.server_address[1],
        timeout=2,
    )
    encoded = None
    headers: dict[str, str] = {"accept": "application/json"}
    if body is not None:
        encoded = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
        headers["content-length"] = str(len(encoded))
    connection.request(method, path, body=encoded, headers=headers)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, payload


def test_authority_request_status_is_read_only() -> None:
    service = FakeAuthorityRequests()
    server, thread = _server(service)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk/authority-request?target=" + TARGET,
        )
        assert status == 200
        assert payload["requestCreated"] is False
        assert payload["effectPerformed"] is False
        assert payload["authorizationGranted"] is False
        assert payload["actionLeaseCreated"] is False
        assert payload["actionAuthority"] is False
        assert payload["readiness"]["ready"] is True
        assert payload["request"] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_authority_request_creation_is_ledger_effect_only() -> None:
    service = FakeAuthorityRequests()
    server, thread = _server(service)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/authority-request/requests",
            {
                "target_inference_receipt_sha256": TARGET,
                "expected_admission_receipt_sha256": ADMISSION,
            },
        )
        assert status == 200
        assert payload["requestCreated"] is True
        assert payload["effectPerformed"] is True
        assert payload["desktopEffectPerformed"] is False
        assert payload["authorizationGranted"] is False
        assert payload["actionLeaseCreated"] is False
        assert payload["actionAuthority"] is False
        assert (
            payload["request"]["request_state"]
            == "PENDING_AUTHORIZATION"
        )
        assert payload["request"]["authorization_granted"] is False
        assert payload["request"]["action_authority"] is False
        assert len(service.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_cannot_supply_requester_or_scope() -> None:
    service = FakeAuthorityRequests()
    server, thread = _server(service)
    try:
        status, _ = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/authority-request/requests",
            {
                "target_inference_receipt_sha256": TARGET,
                "expected_admission_receipt_sha256": ADMISSION,
                "requester_id": "browser:fake",
                "requested_scope_value": "TOGGLE_AIRPLANE_MODE",
            },
        )
        assert status == 400
        assert service.calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
