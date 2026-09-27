from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Any

from phios.macro_ghostwalk_control_server import (
    LOOPBACK_HOST,
    GhostWalkControlServer,
)
from phios.macro_operator_log import OperatorNoteStatus


@dataclass
class FakeSnapshot:
    def to_dict(self) -> dict[str, object]:
        return {}


class FakeSurface:
    def snapshot(self) -> FakeSnapshot:
        return FakeSnapshot()


@dataclass
class FakeNote:
    revision: int
    revision_sha256: str
    body: str
    status: str = "ACTIVE"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "phios.ghostwalk_operator_note.v0.28",
            "target_inference_receipt_sha256": "a" * 64,
            "note_id": "ghostwalk-transition:" + "b" * 64,
            "revision": self.revision,
            "revision_sha256": self.revision_sha256,
            "author_id": "operator:local",
            "body": self.body,
            "tags": [
                "ghostwalk",
                "operator-interpretation",
                "transition-inference",
            ],
            "status": self.status,
            "created_at": "2026-09-27T06:30:00+00:00",
            "supersedes_revision_sha256": (
                None if self.revision == 1 else "c" * 64
            ),
            "inference_status": "CANDIDATES",
            "session_id": "demo",
            "action_observation_sha256": "b" * 64,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }


@dataclass
class FakeOutcome:
    note: FakeNote

    def to_dict(self) -> dict[str, object]:
        return {
            "result": "APPLIED",
            "note": self.note.to_dict(),
            "annotation_mutation": True,
            "desktop_effect_performed": False,
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }


class FakeEditor:
    def __init__(self) -> None:
        self.note = FakeNote(
            revision=1,
            revision_sha256="c" * 64,
            body="Machine summary.",
        )
        self.calls: list[dict[str, Any]] = []

    def view(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> FakeNote:
        assert target_inference_receipt_sha256 == "a" * 64
        return self.note

    def edit(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        body: str,
        status: OperatorNoteStatus = OperatorNoteStatus.ACTIVE,
        created_at: str | None = None,
    ) -> FakeOutcome:
        self.calls.append(
            {
                "target": target_inference_receipt_sha256,
                "expected": expected_current_revision_sha256,
                "body": body,
                "status": status.value,
                "created_at": created_at,
            }
        )
        self.note = FakeNote(
            revision=2,
            revision_sha256="d" * 64,
            body=body,
            status=status.value,
        )
        return FakeOutcome(self.note)


def _server(
    editor: FakeEditor,
) -> tuple[GhostWalkControlServer, threading.Thread]:
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, 0),
        surface=FakeSurface(),  # type: ignore[arg-type]
        editor=editor,  # type: ignore[arg-type]
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


def test_operator_note_get_is_read_only_projection() -> None:
    editor = FakeEditor()
    server, thread = _server(editor)
    try:
        status, payload = _request(
            server,
            "GET",
            "/api/v1/ghostwalk/operator-log?target=" + "a" * 64,
        )
        assert status == 200
        assert (
            payload["transportSchemaVersion"]
            == "phios.ghostwalk-operator-log-transport.v0.28"
        )
        assert payload["annotationMutation"] is False
        assert payload["effectPerformed"] is False
        assert payload["executionAuthority"] is False
        assert payload["note"]["revision"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_operator_note_post_appends_annotation_revision() -> None:
    editor = FakeEditor()
    server, thread = _server(editor)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/operator-log/revisions",
            {
                "target_inference_receipt_sha256": "a" * 64,
                "expected_current_revision_sha256": "c" * 64,
                "body": "Correction: opened network adapter properties.",
                "status": "ACTIVE",
            },
        )
        assert status == 200
        assert payload["annotationMutation"] is True
        assert payload["effectPerformed"] is True
        assert payload["desktopEffectPerformed"] is False
        assert payload["executionAuthority"] is False
        assert payload["outcome"]["note"]["revision"] == 2
        assert editor.calls[0]["status"] == "ACTIVE"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_operator_note_post_rejects_extra_fields() -> None:
    editor = FakeEditor()
    server, thread = _server(editor)
    try:
        status, payload = _request(
            server,
            "POST",
            "/api/v1/ghostwalk/operator-log/revisions",
            {
                "target_inference_receipt_sha256": "a" * 64,
                "expected_current_revision_sha256": "c" * 64,
                "body": "Correction.",
                "status": "ACTIVE",
                "author_id": "browser:should-not-control-this",
            },
        )
        assert status == 400
        assert payload["effectPerformed"] is False
        assert editor.calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
