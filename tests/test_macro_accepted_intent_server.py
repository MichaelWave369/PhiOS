from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.client import HTTPConnection

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentRevision,
    GhostWalkAcceptedIntentStatus,
    GhostWalkIntentFamily,
)
from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)


class FakeSurface:
    def snapshot(self) -> object:
        raise AssertionError("status endpoint not used")


class FakeIntentRegistry:
    def __init__(self) -> None:
        self.current_item: GhostWalkAcceptedIntentRevision | None = None
        self.calls: list[dict[str, object]] = []

    def current(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAcceptedIntentRevision | None:
        self.calls.append(
            {"operation": "CURRENT", "target": target_inference_receipt_sha256}
        )
        return self.current_item

    def accept(
        self,
        *,
        target_inference_receipt_sha256: str,
        source_operator_note_revision_sha256: str,
        intent_family: GhostWalkIntentFamily,
        intent_code: str,
        expected_current_revision_sha256: str | None,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision:
        self.calls.append(
            {
                "operation": "ACCEPT",
                "target": target_inference_receipt_sha256,
                "source": source_operator_note_revision_sha256,
                "family": intent_family.value,
                "code": intent_code,
                "expected": expected_current_revision_sha256,
            }
        )
        item = GhostWalkAcceptedIntentRevision(
            target_inference_receipt_sha256=target_inference_receipt_sha256,
            source_operator_note_revision_sha256=(
                source_operator_note_revision_sha256
            ),
            revision=1 if expected_current_revision_sha256 is None else 2,
            intent_family=intent_family,
            intent_code=intent_code,
            status=GhostWalkAcceptedIntentStatus.ACTIVE,
            accepted_by="operator:local",
            accepted_at="2026-09-27T06:55:00+00:00",
            supersedes_revision_sha256=(
                expected_current_revision_sha256
            ),
        )
        self.current_item = item
        return item

    def revoke(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision:
        self.calls.append(
            {
                "operation": "REVOKE",
                "target": target_inference_receipt_sha256,
                "expected": expected_current_revision_sha256,
            }
        )
        assert self.current_item is not None
        item = GhostWalkAcceptedIntentRevision(
            target_inference_receipt_sha256=target_inference_receipt_sha256,
            source_operator_note_revision_sha256=(
                self.current_item.source_operator_note_revision_sha256
            ),
            revision=self.current_item.revision + 1,
            intent_family=self.current_item.intent_family,
            intent_code=self.current_item.intent_code,
            status=GhostWalkAcceptedIntentStatus.REVOKED,
            accepted_by="operator:local",
            accepted_at="2026-09-27T06:56:00+00:00",
            supersedes_revision_sha256=expected_current_revision_sha256,
        )
        self.current_item = item
        return item


def _server(
    registry: FakeIntentRegistry,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=FakeSurface(),  # type: ignore[arg-type]
        accepted_intents=registry,  # type: ignore[arg-type]
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


def test_get_missing_accepted_intent_returns_404_zero_authority() -> None:
    registry = FakeIntentRegistry()
    server, thread = _server(registry)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk/accepted-intent?target=" + "a" * 64,
        )
        assert status == 404
        assert payload["effectPerformed"] is False
        assert payload["policyAuthority"] is False
        assert payload["executionAuthority"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_accept_intent_is_persistent_non_policy_mutation() -> None:
    registry = FakeIntentRegistry()
    server, thread = _server(registry)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/accepted-intent/revisions",
            {
                "operation": "ACCEPT",
                "target_inference_receipt_sha256": "a" * 64,
                "source_operator_note_revision_sha256": "b" * 64,
                "intent_family": "OPEN",
                "intent_code": "OPEN_NETWORK_ADAPTER_PROPERTIES",
                "expected_current_revision_sha256": None,
            },
        )
        assert status == 200
        assert payload["intentMutation"] is True
        assert payload["effectPerformed"] is True
        assert payload["desktopEffectPerformed"] is False
        assert payload["policyAuthority"] is False
        assert payload["executionAuthority"] is False
        assert payload["intent"]["human_intent_confirmed"] is True
        assert payload["intent"]["intent_code"] == (
            "OPEN_NETWORK_ADAPTER_PROPERTIES"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_revoke_intent_appends_revision() -> None:
    registry = FakeIntentRegistry()
    first = registry.accept(
        target_inference_receipt_sha256="a" * 64,
        source_operator_note_revision_sha256="b" * 64,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
    )
    server, thread = _server(registry)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/accepted-intent/revisions",
            {
                "operation": "REVOKE",
                "target_inference_receipt_sha256": "a" * 64,
                "expected_current_revision_sha256": (
                    first.revision_sha256
                ),
            },
        )
        assert status == 200
        assert payload["intent"]["status"] == "REVOKED"
        assert payload["intent"]["revision"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_cannot_supply_accepted_by_or_policy_authority() -> None:
    registry = FakeIntentRegistry()
    server, thread = _server(registry)
    try:
        status, _ = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/accepted-intent/revisions",
            {
                "operation": "ACCEPT",
                "target_inference_receipt_sha256": "a" * 64,
                "source_operator_note_revision_sha256": "b" * 64,
                "intent_family": "OPEN",
                "intent_code": "OPEN_NETWORK_ADAPTER_PROPERTIES",
                "expected_current_revision_sha256": None,
                "accepted_by": "browser:fake",
                "policyAuthority": True,
            },
        )
        assert status == 400
        assert not any(
            call.get("operation") == "ACCEPT"
            for call in registry.calls
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
