from __future__ import annotations

import json
import threading

import pytest
from http.client import HTTPConnection

from phios.macro_authorization_console import (
    GhostWalkActionLeaseSummary,
    GhostWalkAuthorizationConsoleSnapshot,
    GhostWalkExecutableBindingSummary,
)
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecision,
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationReadiness,
    GhostWalkAuthorizationReadinessReason,
)
from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)

TARGET = "a" * 64
REQUEST = "b" * 64
DECISION = "c" * 64
BINDING = "d" * 64
LEASE = "e" * 64


class FakeSurface:
    def snapshot(self) -> object:
        raise AssertionError("Ghost-Walk status endpoint not used")


class FakeConsole:
    def __init__(self) -> None:
        self.decision_calls: list[dict[str, object]] = []
        self.binding_calls: list[dict[str, object]] = []
        self.lease_calls: list[dict[str, object]] = []

    def snapshot(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationConsoleSnapshot:
        assert target_inference_receipt_sha256 == TARGET
        return GhostWalkAuthorizationConsoleSnapshot(
            target_inference_receipt_sha256=TARGET,
            authorization_readiness=GhostWalkAuthorizationReadiness(
                target_inference_receipt_sha256=TARGET,
                authority_request_sha256=REQUEST,
                latest_decision_sha256=None,
                latest_decision=None,
                ready=True,
                reason=GhostWalkAuthorizationReadinessReason.READY,
                authorization_granted=False,
            ),
            authorization_decision=None,
            binding_available=False,
            binding_readiness=None,
            binding=None,
            lease_available=False,
            lease_readiness=None,
            lease=None,
        )

    def record_decision(self, **kwargs: object) -> GhostWalkAuthorizationDecision:
        self.decision_calls.append(kwargs)
        return GhostWalkAuthorizationDecision(
            authority_request_sha256=REQUEST,
            target_inference_receipt_sha256=TARGET,
            admission_receipt_sha256="1" * 64,
            accepted_intent_revision_sha256="2" * 64,
            policy_profile_sha256="3" * 64,
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            authorizer_id="operator:local",
            decision=GhostWalkAuthorizationDecisionKind.APPROVE,
            decision_sequence=0,
            previous_decision_sha256=None,
            decided_at="2026-09-27T21:40:00+00:00",
            decision_note="approved locally",
            authorization_granted=True,
            request_resolved=True,
        )

    def create_binding(self, **kwargs: object) -> GhostWalkExecutableBindingSummary:
        self.binding_calls.append(kwargs)
        return GhostWalkExecutableBindingSummary(
            executable_binding_sha256=BINDING,
            authorization_decision_sha256=DECISION,
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            mapping_id="ghostwalk.open-network-adapter.desktop-click.v1",
            capability_id="desktop.interaction.click",
            capability_version="0.19.0",
            payload_sha256="4" * 64,
            permissions_required=("ui.interact",),
            effects_declared=("display.control", "filesystem.change"),
            bound_at="2026-09-27T21:41:00+00:00",
        )

    def issue_lease(self, **kwargs: object) -> GhostWalkActionLeaseSummary:
        self.lease_calls.append(kwargs)
        return GhostWalkActionLeaseSummary(
            action_lease_sha256=LEASE,
            lease_record_sha256="5" * 64,
            executable_binding_sha256=BINDING,
            principal_id="operator:local",
            issuer_id="phios:ghostwalk-lease-broker",
            capability_id="desktop.interaction.click",
            capability_version="0.19.0",
            payload_sha256="4" * 64,
            effects_declared=("display.control", "filesystem.change"),
            permissions_authorized=("ui.interact",),
            valid_from="2026-09-27T21:42:00+00:00",
            valid_until="2026-09-27T21:42:30+00:00",
            max_uses=1,
            lease_action_authority=True,
        )


def _server(
    console: FakeConsole,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=FakeSurface(),  # type: ignore[arg-type]
        authorization_console=console,  # type: ignore[arg-type]
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
    extra_headers: dict[str, str] | None = None,
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
    headers.update(extra_headers or {})
    connection.request(method, path, body=encoded, headers=headers)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, payload


def test_authorization_console_status_is_zero_authority() -> None:
    console = FakeConsole()
    server, thread = _server(console)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk/authorization-console?target=" + TARGET,
        )
        assert status == 200
        assert payload["humanAuthorizationSurface"] is True
        assert payload["mutationKind"] == "NONE"
        assert payload["actionAuthority"] is False
        assert payload["executionAuthority"] is False
        assert payload["effectPerformed"] is False
        assert payload["snapshot"]["authorization_readiness"]["ready"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("endpoint", ["decisions", "bindings", "leases"])
@pytest.mark.parametrize("headers", [
    {},
    {"origin": "https://attacker.invalid", "content-type": "text/plain",
     "sec-fetch-site": "cross-site"},
    {"host": "attacker.invalid", "authorization": "Bearer agent-session"},
])
def test_http_never_reaches_operator_services(endpoint: str, headers: dict[str, str]) -> None:
    console = FakeConsole()
    server, thread = _server(console)
    try:
        status, payload = _request(
            server, "POST", "/api/v1/ghostwalk/authorization-console/" + endpoint,
            {"target_inference_receipt_sha256": TARGET,
             "expected_authority_request_sha256": REQUEST,
             "expected_previous_decision_sha256": None,
             "decision": "APPROVE", "decision_note": "forged human approval"},
            headers,
        )
        assert status == 403
        assert payload["error"] == "operator_channel_required"
        assert payload["actionAuthority"] is False
        assert payload["executionAuthority"] is False
        assert payload["effectPerformed"] is False
        assert console.decision_calls == console.binding_calls == console.lease_calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
