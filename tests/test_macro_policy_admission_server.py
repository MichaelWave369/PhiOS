from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)
from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionProjection,
    GhostWalkPolicyAdmissionReceipt,
    GhostWalkPolicyDecision,
    GhostWalkPolicyProfile,
    GhostWalkPolicyReason,
)

TARGET = "a" * 64
INTENT = "b" * 64
NOTE = "c" * 64


class FakeSurface:
    def snapshot(self) -> object:
        raise AssertionError("status endpoint not used")


class FakePolicyAdmission:
    def __init__(self) -> None:
        self.profile = GhostWalkPolicyProfile(
            profile_id="ghostwalk-policy:test",
            allow_request_intent_codes=(
                "OPEN_NETWORK_ADAPTER_PROPERTIES",
            ),
            deny_intent_codes=(),
        )
        self.record_calls: list[dict[str, str]] = []

    def project(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkPolicyAdmissionProjection:
        assert target_inference_receipt_sha256 == TARGET
        return GhostWalkPolicyAdmissionProjection(
            target_inference_receipt_sha256=TARGET,
            accepted_intent_revision_sha256=INTENT,
            source_operator_note_revision_sha256=NOTE,
            current_operator_note_revision_sha256=NOTE,
            policy_profile_sha256=self.profile.profile_sha256,
            intent_family="OPEN",
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            accepted_intent_status="ACTIVE",
            operator_binding_current=True,
            decision=GhostWalkPolicyDecision.ALLOW_REQUEST,
            reason=GhostWalkPolicyReason.INTENT_EXPLICITLY_ALLOWED,
            request_authority_eligible=True,
        )

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_accepted_intent_revision_sha256: str,
        expected_policy_profile_sha256: str,
        evaluated_at: str | None = None,
    ) -> GhostWalkPolicyAdmissionReceipt:
        self.record_calls.append(
            {
                "target": target_inference_receipt_sha256,
                "intent": expected_accepted_intent_revision_sha256,
                "profile": expected_policy_profile_sha256,
            }
        )
        projection = self.project(
            target_inference_receipt_sha256=(
                target_inference_receipt_sha256
            )
        )
        return GhostWalkPolicyAdmissionReceipt(
            projection_sha256=projection.projection_sha256,
            target_inference_receipt_sha256=TARGET,
            accepted_intent_revision_sha256=INTENT,
            policy_profile_sha256=self.profile.profile_sha256,
            decision=GhostWalkPolicyDecision.ALLOW_REQUEST,
            reason=GhostWalkPolicyReason.INTENT_EXPLICITLY_ALLOWED,
            request_authority_eligible=True,
            evaluated_at="2026-09-27T07:15:00+00:00",
        )


def _server(
    service: FakePolicyAdmission,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=FakeSurface(),  # type: ignore[arg-type]
        policy_admission=service,  # type: ignore[arg-type]
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


def test_policy_projection_is_read_only_and_zero_authority() -> None:
    service = FakePolicyAdmission()
    server, thread = _server(service)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk/policy-admission?target=" + TARGET,
        )
        assert status == 200
        assert payload["effectPerformed"] is False
        assert payload["admissionRecorded"] is False
        assert payload["authorityRequestCreated"] is False
        assert payload["actionLeaseCreated"] is False
        assert payload["actionAuthority"] is False
        assert payload["projection"]["decision"] == "ALLOW_REQUEST"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_recorded_admission_is_ledger_effect_not_authority() -> None:
    service = FakePolicyAdmission()
    server, thread = _server(service)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/policy-admission/evaluations",
            {
                "target_inference_receipt_sha256": TARGET,
                "expected_accepted_intent_revision_sha256": INTENT,
                "expected_policy_profile_sha256": (
                    service.profile.profile_sha256
                ),
            },
        )
        assert status == 200
        assert payload["effectPerformed"] is True
        assert payload["admissionRecorded"] is True
        assert payload["desktopEffectPerformed"] is False
        assert payload["authorityRequestCreated"] is False
        assert payload["actionLeaseCreated"] is False
        assert payload["executionAuthority"] is False
        assert payload["receipt"]["request_authority_eligible"] is True
        assert len(service.record_calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_cannot_inject_authority_into_policy_record() -> None:
    service = FakePolicyAdmission()
    server, thread = _server(service)
    try:
        status, _ = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/policy-admission/evaluations",
            {
                "target_inference_receipt_sha256": TARGET,
                "expected_accepted_intent_revision_sha256": INTENT,
                "expected_policy_profile_sha256": (
                    service.profile.profile_sha256
                ),
                "actionAuthority": True,
            },
        )
        assert status == 400
        assert service.record_calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
