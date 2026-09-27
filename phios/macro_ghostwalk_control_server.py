"""Loopback Ghost-Walk control bridge for Macro Runtime v0.26.

The process owns one long-lived v0.24 host and exposes only the zero-authority
v0.25 control surface. Browser callers never receive listener, UIA, baseline
service, ActionLease, or execution primitive objects.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import parse_qs, urlsplit

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentError,
    GhostWalkAcceptedIntentRegistry,
    GhostWalkAcceptedIntentRevision,
    GhostWalkIntentFamily,
)
from phios.macro_ghostwalk_control_surface import (
    GhostWalkControlAction,
    GhostWalkControlOutcome,
    GhostWalkControlSnapshot,
    GhostWalkControlSurface,
)
from phios.macro_ghostwalk_host_service import GhostWalkHostService
from phios.macro_ghostwalk_operator_editor import (
    GhostWalkOperatorEditOutcome,
    GhostWalkOperatorEditor,
    GhostWalkOperatorEditorError,
    GhostWalkOperatorNoteView,
)
from phios.macro_operator_log import OperatorNoteStatus
from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionError,
    GhostWalkPolicyAdmissionProjection,
    GhostWalkPolicyAdmissionReceipt,
    GhostWalkPolicyAdmissionService,
    GhostWalkPolicyProfile,
)
from phios.spine.ledger import RealityLedger

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_GHOSTWALK_PORT = 3973
MAX_REQUEST_BYTES = 8192
TRANSPORT_SCHEMA_VERSION = "phios.ghostwalk-control-transport.v0.26"
TRANSPORT_IDENTITY = "phios-ghostwalk-control"
OPERATOR_TRANSPORT_SCHEMA_VERSION = (
    "phios.ghostwalk-operator-log-transport.v0.28"
)
OPERATOR_TRANSPORT_IDENTITY = "phios-ghostwalk-operator-editor"
ACCEPTED_INTENT_TRANSPORT_SCHEMA_VERSION = (
    "phios.ghostwalk-accepted-intent-transport.v0.29"
)
ACCEPTED_INTENT_TRANSPORT_IDENTITY = "phios-ghostwalk-accepted-intent"
POLICY_ADMISSION_TRANSPORT_SCHEMA_VERSION = (
    "phios.ghostwalk-policy-admission-transport.v0.30"
)
POLICY_ADMISSION_TRANSPORT_IDENTITY = "phios-ghostwalk-policy-admission"
DEFAULT_HOST_ID = "ghostwalk-host:local"
DEFAULT_BASELINE_SERVICE_ID = "ghostwalk-baseline:local"
DEFAULT_COORDINATOR_ID = "ghostwalk-coordinator:local"
DEFAULT_LISTENER_ID = "ghostwalk-listener:local"
DEFAULT_SURFACE_ID = "ghostwalk-control:local"
DEFAULT_OPERATOR_AUTHOR_ID = "operator:local"


class GhostWalkControlBridgeError(ValueError):
    """Raised when a loopback control request is malformed."""


class GhostWalkSurface(Protocol):
    def snapshot(self) -> GhostWalkControlSnapshot: ...

    def apply(
        self,
        *,
        action: GhostWalkControlAction,
        session_id: str | None = None,
    ) -> GhostWalkControlOutcome: ...


class GhostWalkOperatorEditorPort(Protocol):
    def view(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkOperatorNoteView: ...

    def edit(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        body: str,
        status: OperatorNoteStatus = OperatorNoteStatus.ACTIVE,
        created_at: str | None = None,
    ) -> GhostWalkOperatorEditOutcome: ...


class GhostWalkAcceptedIntentPort(Protocol):
    def current(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAcceptedIntentRevision | None: ...

    def accept(
        self,
        *,
        target_inference_receipt_sha256: str,
        source_operator_note_revision_sha256: str,
        intent_family: GhostWalkIntentFamily,
        intent_code: str,
        expected_current_revision_sha256: str | None,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision: ...

    def revoke(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_current_revision_sha256: str,
        accepted_at: str | None = None,
    ) -> GhostWalkAcceptedIntentRevision: ...


class GhostWalkPolicyAdmissionPort(Protocol):
    profile: GhostWalkPolicyProfile

    def project(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkPolicyAdmissionProjection: ...

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_accepted_intent_revision_sha256: str,
        expected_policy_profile_sha256: str,
        evaluated_at: str | None = None,
    ) -> GhostWalkPolicyAdmissionReceipt: ...



def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _transport_base() -> dict[str, object]:
    return {
        "transportSchemaVersion": TRANSPORT_SCHEMA_VERSION,
        "transport": "loopback-http",
        "transportIdentity": TRANSPORT_IDENTITY,
        "localOnly": True,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": False,
    }


def _operator_transport_base(
    *,
    effect_performed: bool,
) -> dict[str, object]:
    return {
        "transportSchemaVersion": OPERATOR_TRANSPORT_SCHEMA_VERSION,
        "transport": "loopback-http",
        "transportIdentity": OPERATOR_TRANSPORT_IDENTITY,
        "localOnly": True,
        "annotationMutation": effect_performed,
        "desktopEffectPerformed": False,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": effect_performed,
    }


def operator_note_envelope(
    editor: GhostWalkOperatorEditorPort,
    *,
    target_inference_receipt_sha256: str,
) -> dict[str, object]:
    payload = _operator_transport_base(effect_performed=False)
    payload.update(
        {
            "servedAt": _utc_now(),
            "note": editor.view(
                target_inference_receipt_sha256=(
                    target_inference_receipt_sha256
                )
            ).to_dict(),
        }
    )
    return payload


def operator_edit_envelope(
    editor: GhostWalkOperatorEditorPort,
    *,
    target_inference_receipt_sha256: str,
    expected_current_revision_sha256: str,
    body: str,
    status: OperatorNoteStatus,
) -> dict[str, object]:
    outcome = editor.edit(
        target_inference_receipt_sha256=(
            target_inference_receipt_sha256
        ),
        expected_current_revision_sha256=(
            expected_current_revision_sha256
        ),
        body=body,
        status=status,
    )
    payload = _operator_transport_base(effect_performed=True)
    payload.update(
        {
            "servedAt": _utc_now(),
            "outcome": outcome.to_dict(),
        }
    )
    return payload


def parse_operator_edit_payload(
    payload: object,
) -> tuple[str, str, str, OperatorNoteStatus]:
    if not isinstance(payload, Mapping):
        raise GhostWalkControlBridgeError(
            "OperatorLog edit body must be an object"
        )
    expected_keys = {
        "target_inference_receipt_sha256",
        "expected_current_revision_sha256",
        "body",
        "status",
    }
    if set(payload) != expected_keys:
        raise GhostWalkControlBridgeError(
            "OperatorLog edit fields do not match contract"
        )

    target = payload.get("target_inference_receipt_sha256")
    expected = payload.get("expected_current_revision_sha256")
    body = payload.get("body")
    raw_status = payload.get("status")

    if (
        not isinstance(target, str)
        or not re.fullmatch(r"[0-9a-f]{64}", target)
    ):
        raise GhostWalkControlBridgeError(
            "target inference receipt must be a SHA-256 digest"
        )
    if (
        not isinstance(expected, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected)
    ):
        raise GhostWalkControlBridgeError(
            "expected revision must be a SHA-256 digest"
        )
    if (
        not isinstance(body, str)
        or not body
        or len(body) > 16384
        or any(
            ord(char) < 32 and char not in "\n\r\t"
            for char in body
        )
    ):
        raise GhostWalkControlBridgeError(
            "operator note body is invalid"
        )
    if not isinstance(raw_status, str):
        raise GhostWalkControlBridgeError(
            "operator note status must be a string"
        )
    try:
        status = OperatorNoteStatus(raw_status)
    except ValueError as exc:
        raise GhostWalkControlBridgeError(
            "operator note status is unsupported"
        ) from exc
    return target, expected, body, status


def _accepted_intent_transport_base(
    *,
    effect_performed: bool,
) -> dict[str, object]:
    return {
        "transportSchemaVersion": (
            ACCEPTED_INTENT_TRANSPORT_SCHEMA_VERSION
        ),
        "transport": "loopback-http",
        "transportIdentity": ACCEPTED_INTENT_TRANSPORT_IDENTITY,
        "localOnly": True,
        "intentMutation": effect_performed,
        "desktopEffectPerformed": False,
        "policyAuthority": False,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": effect_performed,
    }


def accepted_intent_envelope(
    registry: GhostWalkAcceptedIntentPort,
    *,
    target_inference_receipt_sha256: str,
) -> dict[str, object] | None:
    current = registry.current(
        target_inference_receipt_sha256=(
            target_inference_receipt_sha256
        )
    )
    if current is None:
        return None
    payload = _accepted_intent_transport_base(effect_performed=False)
    payload.update(
        {
            "servedAt": _utc_now(),
            "intent": current.to_dict(),
        }
    )
    return payload


def accepted_intent_mutation_envelope(
    revision: GhostWalkAcceptedIntentRevision,
) -> dict[str, object]:
    payload = _accepted_intent_transport_base(effect_performed=True)
    payload.update(
        {
            "servedAt": _utc_now(),
            "intent": revision.to_dict(),
        }
    )
    return payload


def parse_accepted_intent_payload(
    payload: object,
) -> tuple[
    str,
    str,
    str | None,
    GhostWalkIntentFamily | None,
    str | None,
    str | None,
]:
    if not isinstance(payload, Mapping):
        raise GhostWalkControlBridgeError(
            "accepted-intent body must be an object"
        )
    operation = payload.get("operation")
    if operation == "ACCEPT":
        expected_keys = {
            "operation",
            "target_inference_receipt_sha256",
            "source_operator_note_revision_sha256",
            "intent_family",
            "intent_code",
            "expected_current_revision_sha256",
        }
        if set(payload) != expected_keys:
            raise GhostWalkControlBridgeError(
                "accepted-intent ACCEPT fields do not match contract"
            )
        target = payload.get("target_inference_receipt_sha256")
        source_note = payload.get(
            "source_operator_note_revision_sha256"
        )
        expected = payload.get("expected_current_revision_sha256")
        raw_family = payload.get("intent_family")
        intent_code = payload.get("intent_code")
        if (
            not isinstance(target, str)
            or re.fullmatch(r"[0-9a-f]{64}", target) is None
            or not isinstance(source_note, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_note) is None
            or (
                expected is not None
                and (
                    not isinstance(expected, str)
                    or re.fullmatch(r"[0-9a-f]{64}", expected) is None
                )
            )
            or not isinstance(raw_family, str)
            or not isinstance(intent_code, str)
        ):
            raise GhostWalkControlBridgeError(
                "accepted-intent ACCEPT values are invalid"
            )
        try:
            family = GhostWalkIntentFamily(raw_family)
        except ValueError as exc:
            raise GhostWalkControlBridgeError(
                "accepted-intent family is unsupported"
            ) from exc
        if (
            not intent_code
            or len(intent_code) > 128
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", intent_code)
            is None
        ):
            raise GhostWalkControlBridgeError(
                "accepted-intent code is invalid"
            )
        return (
            operation,
            target,
            expected,
            family,
            intent_code,
            source_note,
        )

    if operation == "REVOKE":
        expected_keys = {
            "operation",
            "target_inference_receipt_sha256",
            "expected_current_revision_sha256",
        }
        if set(payload) != expected_keys:
            raise GhostWalkControlBridgeError(
                "accepted-intent REVOKE fields do not match contract"
            )
        target = payload.get("target_inference_receipt_sha256")
        expected = payload.get("expected_current_revision_sha256")
        if (
            not isinstance(target, str)
            or re.fullmatch(r"[0-9a-f]{64}", target) is None
            or not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            raise GhostWalkControlBridgeError(
                "accepted-intent REVOKE values are invalid"
            )
        return operation, target, expected, None, None, None

    raise GhostWalkControlBridgeError(
        "accepted-intent operation is unsupported"
    )


def _policy_admission_transport_base(
    *,
    effect_performed: bool,
) -> dict[str, object]:
    return {
        "transportSchemaVersion": (
            POLICY_ADMISSION_TRANSPORT_SCHEMA_VERSION
        ),
        "transport": "loopback-http",
        "transportIdentity": POLICY_ADMISSION_TRANSPORT_IDENTITY,
        "localOnly": True,
        "admissionRecorded": effect_performed,
        "desktopEffectPerformed": False,
        "authorityRequestCreated": False,
        "actionLeaseCreated": False,
        "policyAuthority": False,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": effect_performed,
    }


def policy_admission_projection_envelope(
    service: GhostWalkPolicyAdmissionPort,
    *,
    target_inference_receipt_sha256: str,
) -> dict[str, object]:
    projection = service.project(
        target_inference_receipt_sha256=(
            target_inference_receipt_sha256
        )
    )
    payload = _policy_admission_transport_base(
        effect_performed=False
    )
    payload.update(
        {
            "servedAt": _utc_now(),
            "profile": service.profile.to_dict(),
            "projection": projection.to_dict(),
        }
    )
    return payload


def policy_admission_record_envelope(
    service: GhostWalkPolicyAdmissionPort,
    *,
    target_inference_receipt_sha256: str,
    expected_accepted_intent_revision_sha256: str,
    expected_policy_profile_sha256: str,
) -> dict[str, object]:
    receipt = service.record(
        target_inference_receipt_sha256=(
            target_inference_receipt_sha256
        ),
        expected_accepted_intent_revision_sha256=(
            expected_accepted_intent_revision_sha256
        ),
        expected_policy_profile_sha256=(
            expected_policy_profile_sha256
        ),
    )
    payload = _policy_admission_transport_base(
        effect_performed=True
    )
    payload.update(
        {
            "servedAt": _utc_now(),
            "profile": service.profile.to_dict(),
            "receipt": receipt.to_dict(),
        }
    )
    return payload


def parse_policy_admission_record_payload(
    payload: object,
) -> tuple[str, str, str]:
    if not isinstance(payload, Mapping):
        raise GhostWalkControlBridgeError(
            "policy-admission record body must be an object"
        )
    expected_keys = {
        "target_inference_receipt_sha256",
        "expected_accepted_intent_revision_sha256",
        "expected_policy_profile_sha256",
    }
    if set(payload) != expected_keys:
        raise GhostWalkControlBridgeError(
            "policy-admission record fields do not match contract"
        )
    target = payload.get("target_inference_receipt_sha256")
    expected_intent = payload.get(
        "expected_accepted_intent_revision_sha256"
    )
    expected_profile = payload.get(
        "expected_policy_profile_sha256"
    )
    for value, field in (
        (target, "target inference receipt"),
        (expected_intent, "expected accepted intent revision"),
        (expected_profile, "expected policy profile"),
    ):
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
        ):
            raise GhostWalkControlBridgeError(
                f"{field} must be a SHA-256 digest"
            )
    assert isinstance(target, str)
    assert isinstance(expected_intent, str)
    assert isinstance(expected_profile, str)
    return target, expected_intent, expected_profile


def status_envelope(surface: GhostWalkSurface) -> dict[str, object]:
    payload = _transport_base()
    payload.update(
        {
            "servedAt": _utc_now(),
            "snapshot": surface.snapshot().to_dict(),
        }
    )
    return payload


def action_envelope(
    surface: GhostWalkSurface,
    *,
    action: GhostWalkControlAction,
    session_id: str | None,
) -> dict[str, object]:
    outcome = surface.apply(action=action, session_id=session_id)
    payload = _transport_base()
    payload.update(
        {
            "servedAt": _utc_now(),
            "controlPlaneMutation": (
                outcome.receipt.result.value == "APPLIED"
            ),
            "receipt": outcome.receipt.to_dict(),
            "snapshot": outcome.snapshot.to_dict(),
        }
    )
    return payload


def parse_action_payload(
    payload: object,
) -> tuple[GhostWalkControlAction, str | None]:
    if not isinstance(payload, Mapping):
        raise GhostWalkControlBridgeError(
            "Ghost-Walk action body must be an object"
        )

    keys = set(payload)
    if not keys <= {"action", "session_id"} or "action" not in keys:
        raise GhostWalkControlBridgeError(
            "Ghost-Walk action fields must be action and optional session_id"
        )

    raw_action = payload.get("action")
    if not isinstance(raw_action, str):
        raise GhostWalkControlBridgeError("action must be a string")
    try:
        action = GhostWalkControlAction(raw_action)
    except ValueError as exc:
        raise GhostWalkControlBridgeError(
            "unsupported Ghost-Walk control action"
        ) from exc

    raw_session = payload.get("session_id")
    session_id: str | None
    if raw_session is None:
        session_id = None
    elif (
        isinstance(raw_session, str)
        and raw_session
        and len(raw_session) <= 512
        and not any(ord(char) < 32 for char in raw_session)
    ):
        session_id = raw_session
    else:
        raise GhostWalkControlBridgeError(
            "session_id must be a bounded non-empty string or null"
        )

    if action is GhostWalkControlAction.START:
        if session_id is None:
            raise GhostWalkControlBridgeError(
                "START requires session_id"
            )
    elif session_id is not None:
        raise GhostWalkControlBridgeError(
            "session_id is only valid for START"
        )

    return action, session_id


class GhostWalkControlHandler(BaseHTTPRequestHandler):
    server: "GhostWalkControlServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(
        self,
        status: HTTPStatus,
        body: dict[str, object],
    ) -> None:
        encoded = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        self.send_response(status.value)
        self.send_header(
            "content-type",
            "application/json; charset=utf-8",
        )
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header(
            "cross-origin-resource-policy",
            "same-origin",
        )
        self.send_header("referrer-policy", "no-referrer")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(
        self,
        status: HTTPStatus,
        code: str,
    ) -> None:
        body = _transport_base()
        body.update({"error": code, "servedAt": _utc_now()})
        self._json(status, body)

    def _operator_error(
        self,
        status: HTTPStatus,
        code: str,
    ) -> None:
        body = _operator_transport_base(effect_performed=False)
        body.update({"error": code, "servedAt": _utc_now()})
        self._json(status, body)

    def _accepted_intent_error(
        self,
        status: HTTPStatus,
        code: str,
    ) -> None:
        body = _accepted_intent_transport_base(effect_performed=False)
        body.update({"error": code, "servedAt": _utc_now()})
        self._json(status, body)

    def _policy_admission_error(
        self,
        status: HTTPStatus,
        code: str,
    ) -> None:
        body = _policy_admission_transport_base(
            effect_performed=False
        )
        body.update({"error": code, "servedAt": _utc_now()})
        self._json(status, body)

    def _read_json(
        self,
        *,
        max_bytes: int = MAX_REQUEST_BYTES,
    ) -> object:
        raw_length = self.headers.get("content-length")
        if raw_length is None:
            raise GhostWalkControlBridgeError(
                "content-length is required"
            )
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise GhostWalkControlBridgeError(
                "content-length must be an integer"
            ) from exc
        if length < 1 or length > max_bytes:
            raise GhostWalkControlBridgeError(
                "request body length is outside the allowed bound"
            )
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise GhostWalkControlBridgeError(
                "request body ended before content-length"
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GhostWalkControlBridgeError(
                "request body must be UTF-8 JSON"
            ) from exc

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)

        if parsed.path == "/api/v1/ghostwalk/policy-admission":
            if self.server.policy_admission is None:
                self._policy_admission_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_policy_admission_unavailable",
                )
                return
            try:
                query = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=True,
                )
            except ValueError:
                self._policy_admission_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_policy_admission_request",
                )
                return
            targets = query.get("target")
            if (
                set(query) != {"target"}
                or targets is None
                or len(targets) != 1
                or re.fullmatch(r"[0-9a-f]{64}", targets[0]) is None
            ):
                self._policy_admission_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_policy_admission_request",
                )
                return
            try:
                envelope = policy_admission_projection_envelope(
                    self.server.policy_admission,
                    target_inference_receipt_sha256=targets[0],
                )
            except GhostWalkPolicyAdmissionError as exc:
                code = (
                    "ghostwalk_policy_admission_not_ready"
                    if "does not exist" in str(exc)
                    else "ghostwalk_policy_admission_invalid_evidence"
                )
                self._policy_admission_error(
                    HTTPStatus.NOT_FOUND
                    if code.endswith("not_ready")
                    else HTTPStatus.CONFLICT,
                    code,
                )
                return
            self._json(HTTPStatus.OK, envelope)
            return

        if parsed.path == "/api/v1/ghostwalk/accepted-intent":
            if self.server.accepted_intents is None:
                self._accepted_intent_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_accepted_intent_unavailable",
                )
                return
            try:
                query = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=True,
                )
            except ValueError:
                self._accepted_intent_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_accepted_intent_request",
                )
                return
            targets = query.get("target")
            if (
                set(query) != {"target"}
                or targets is None
                or len(targets) != 1
                or re.fullmatch(r"[0-9a-f]{64}", targets[0]) is None
            ):
                self._accepted_intent_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_accepted_intent_request",
                )
                return
            try:
                intent_envelope = accepted_intent_envelope(
                    self.server.accepted_intents,
                    target_inference_receipt_sha256=targets[0],
                )
            except GhostWalkAcceptedIntentError:
                self._accepted_intent_error(
                    HTTPStatus.CONFLICT,
                    "ghostwalk_accepted_intent_invalid_history",
                )
                return
            if intent_envelope is None:
                self._accepted_intent_error(
                    HTTPStatus.NOT_FOUND,
                    "ghostwalk_accepted_intent_not_found",
                )
                return
            self._json(HTTPStatus.OK, intent_envelope)
            return

        if parsed.path == "/api/v1/ghostwalk/operator-log":
            if self.server.editor is None:
                self._operator_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_operator_editor_unavailable",
                )
                return
            try:
                query = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=True,
                )
            except ValueError:
                self._operator_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_operator_note_request",
                )
                return
            targets = query.get("target")
            if (
                set(query) != {"target"}
                or targets is None
                or len(targets) != 1
                or re.fullmatch(r"[0-9a-f]{64}", targets[0]) is None
            ):
                self._operator_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_operator_note_request",
                )
                return
            try:
                envelope = operator_note_envelope(
                    self.server.editor,
                    target_inference_receipt_sha256=targets[0],
                )
            except GhostWalkOperatorEditorError:
                self._operator_error(
                    HTTPStatus.NOT_FOUND,
                    "ghostwalk_operator_note_not_found",
                )
                return
            self._json(HTTPStatus.OK, envelope)
            return

        if (
            parsed.path != "/api/v1/ghostwalk"
            or parsed.query
            or parsed.fragment
        ):
            self._error(HTTPStatus.NOT_FOUND, "not_found")
            return
        self._json(
            HTTPStatus.OK,
            status_envelope(self.server.surface),
        )

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)

        if parsed.path == "/api/v1/ghostwalk/policy-admission/evaluations":
            if parsed.query or parsed.fragment:
                self._policy_admission_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_policy_admission_record",
                )
                return
            if self.server.policy_admission is None:
                self._policy_admission_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_policy_admission_unavailable",
                )
                return
            try:
                target, expected_intent, expected_profile = (
                    parse_policy_admission_record_payload(
                        self._read_json()
                    )
                )
            except GhostWalkControlBridgeError:
                self._policy_admission_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_policy_admission_record",
                )
                return
            try:
                envelope = policy_admission_record_envelope(
                    self.server.policy_admission,
                    target_inference_receipt_sha256=target,
                    expected_accepted_intent_revision_sha256=(
                        expected_intent
                    ),
                    expected_policy_profile_sha256=expected_profile,
                )
            except GhostWalkPolicyAdmissionError as exc:
                conflict = "changed before" in str(exc)
                self._policy_admission_error(
                    HTTPStatus.CONFLICT
                    if conflict
                    else HTTPStatus.BAD_REQUEST,
                    (
                        "ghostwalk_policy_admission_conflict"
                        if conflict
                        else "ghostwalk_policy_admission_rejected"
                    ),
                )
                return
            self._json(HTTPStatus.OK, envelope)
            return

        if parsed.path == "/api/v1/ghostwalk/accepted-intent/revisions":
            if parsed.query or parsed.fragment:
                self._accepted_intent_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_accepted_intent_mutation",
                )
                return
            if self.server.accepted_intents is None:
                self._accepted_intent_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_accepted_intent_unavailable",
                )
                return
            try:
                (
                    operation,
                    target,
                    expected,
                    family,
                    intent_code,
                    source_note,
                ) = parse_accepted_intent_payload(self._read_json())
            except GhostWalkControlBridgeError:
                self._accepted_intent_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_accepted_intent_mutation",
                )
                return

            try:
                if operation == "ACCEPT":
                    if (
                        family is None
                        or intent_code is None
                        or source_note is None
                    ):
                        raise GhostWalkAcceptedIntentError(
                            "accepted-intent ACCEPT parse was incomplete"
                        )
                    revision = self.server.accepted_intents.accept(
                        target_inference_receipt_sha256=target,
                        source_operator_note_revision_sha256=source_note,
                        intent_family=family,
                        intent_code=intent_code,
                        expected_current_revision_sha256=expected,
                    )
                else:
                    if expected is None:
                        raise GhostWalkAcceptedIntentError(
                            "accepted-intent REVOKE parse was incomplete"
                        )
                    revision = self.server.accepted_intents.revoke(
                        target_inference_receipt_sha256=target,
                        expected_current_revision_sha256=expected,
                    )
            except GhostWalkAcceptedIntentError as exc:
                text = str(exc)
                conflict = (
                    "changed before" in text
                    or "prior history" in text
                )
                self._accepted_intent_error(
                    HTTPStatus.CONFLICT if conflict else HTTPStatus.BAD_REQUEST,
                    (
                        "ghostwalk_accepted_intent_conflict"
                        if conflict
                        else "ghostwalk_accepted_intent_rejected"
                    ),
                )
                return

            self._json(
                HTTPStatus.OK,
                accepted_intent_mutation_envelope(revision),
            )
            return

        if parsed.path == "/api/v1/ghostwalk/operator-log/revisions":
            if parsed.query or parsed.fragment:
                self._operator_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_operator_edit_request",
                )
                return
            if self.server.editor is None:
                self._operator_error(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "ghostwalk_operator_editor_unavailable",
                )
                return
            try:
                target, expected, body, status = (
                    parse_operator_edit_payload(
                        self._read_json(max_bytes=32768)
                    )
                )
            except GhostWalkControlBridgeError:
                self._operator_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_ghostwalk_operator_edit_request",
                )
                return
            try:
                envelope = operator_edit_envelope(
                    self.server.editor,
                    target_inference_receipt_sha256=target,
                    expected_current_revision_sha256=expected,
                    body=body,
                    status=status,
                )
            except GhostWalkOperatorEditorError as exc:
                code = (
                    "ghostwalk_operator_edit_conflict"
                    if "revision changed before edit" in str(exc)
                    else "ghostwalk_operator_edit_rejected"
                )
                self._operator_error(HTTPStatus.CONFLICT, code)
                return
            self._json(HTTPStatus.OK, envelope)
            return

        if (
            parsed.path != "/api/v1/ghostwalk/actions"
            or parsed.query
            or parsed.fragment
        ):
            self._error(HTTPStatus.NOT_FOUND, "not_found")
            return

        try:
            action, session_id = parse_action_payload(
                self._read_json()
            )
        except GhostWalkControlBridgeError:
            self._error(
                HTTPStatus.BAD_REQUEST,
                "invalid_ghostwalk_control_request",
            )
            return

        self._json(
            HTTPStatus.OK,
            action_envelope(
                self.server.surface,
                action=action,
                session_id=session_id,
            ),
        )

    def do_PUT(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")

    def do_PATCH(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")

    def do_DELETE(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")


class GhostWalkControlServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        *,
        surface: GhostWalkSurface,
        editor: GhostWalkOperatorEditorPort | None = None,
        accepted_intents: GhostWalkAcceptedIntentPort | None = None,
        policy_admission: GhostWalkPolicyAdmissionPort | None = None,
        stop_callback: Callable[[], object] | None = None,
    ) -> None:
        if address[0] != LOOPBACK_HOST:
            raise GhostWalkControlBridgeError(
                "Ghost-Walk control server must bind IPv4 loopback"
            )
        self.surface = surface
        self.editor = editor
        self.accepted_intents = accepted_intents
        self.policy_admission = policy_admission
        self._stop_callback = stop_callback
        super().__init__(address, GhostWalkControlHandler)

    def close_owned_runtime(self) -> None:
        if self._stop_callback is not None:
            self._stop_callback()


def default_state_root() -> Path:
    configured = os.environ.get("PHIOS_STATE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".phios"


def default_port() -> int:
    raw = os.environ.get("PHIOS_GHOSTWALK_PORT")
    if raw is None:
        return DEFAULT_GHOSTWALK_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise GhostWalkControlBridgeError(
            "PHIOS_GHOSTWALK_PORT must be an integer"
        ) from exc
    if not 1024 <= port <= 65535:
        raise GhostWalkControlBridgeError(
            "PHIOS_GHOSTWALK_PORT must be from 1024 to 65535"
        )
    return port


def build_local_runtime(
    *,
    state_root: Path,
) -> tuple[
    GhostWalkHostService,
    GhostWalkControlSurface,
]:
    ledger = RealityLedger(
        state_root.expanduser() / "ledger" / "receipts.jsonl"
    )
    host = GhostWalkHostService.from_windows(
        ledger=ledger,
        host_id=DEFAULT_HOST_ID,
        baseline_service_id=DEFAULT_BASELINE_SERVICE_ID,
        coordinator_id=DEFAULT_COORDINATOR_ID,
        listener_id=DEFAULT_LISTENER_ID,
        operator_author_id=DEFAULT_OPERATOR_AUTHOR_ID,
    )
    surface = GhostWalkControlSurface(
        ledger=ledger,
        host=host,
        surface_id=DEFAULT_SURFACE_ID,
    )
    return host, surface


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=default_port(),
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=default_state_root(),
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit(
            "Ghost-Walk control host currently requires Windows"
        )
    if not 1024 <= args.port <= 65535:
        raise SystemExit("port must be from 1024 to 65535")

    host, surface = build_local_runtime(
        state_root=args.state_root,
    )
    editor = GhostWalkOperatorEditor(
        ledger=RealityLedger(
            args.state_root.expanduser()
            / "ledger"
            / "receipts.jsonl"
        ),
        author_id=DEFAULT_OPERATOR_AUTHOR_ID,
    )
    accepted_intents = GhostWalkAcceptedIntentRegistry(
        ledger=RealityLedger(
            args.state_root.expanduser()
            / "ledger"
            / "receipts.jsonl"
        ),
        accepted_by=DEFAULT_OPERATOR_AUTHOR_ID,
    )
    policy_admission = GhostWalkPolicyAdmissionService(
        ledger=RealityLedger(
            args.state_root.expanduser()
            / "ledger"
            / "receipts.jsonl"
        ),
        accepted_intents=accepted_intents,
        operator_editor=editor,
        profile=GhostWalkPolicyProfile.from_environment(os.environ),
    )
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, args.port),
        surface=surface,
        editor=editor,
        accepted_intents=accepted_intents,
        policy_admission=policy_admission,
        stop_callback=host.stop,
    )

    try:
        print(
            "PhiOS Ghost-Walk control: "
            f"http://{LOOPBACK_HOST}:{args.port}"
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if host.active:
                server.close_owned_runtime()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
