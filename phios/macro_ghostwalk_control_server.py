"""Loopback Ghost-Walk control bridge for Macro Runtime v0.26.

The process owns one long-lived v0.24 host and exposes only the zero-authority
v0.25 control surface. Browser callers never receive listener, UIA, baseline
service, ActionLease, or execution primitive objects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit

from phios.macro_ghostwalk_control_surface import (
    GhostWalkControlAction,
    GhostWalkControlOutcome,
    GhostWalkControlSnapshot,
    GhostWalkControlSurface,
)
from phios.macro_ghostwalk_host_service import GhostWalkHostService
from phios.spine.ledger import RealityLedger

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_GHOSTWALK_PORT = 3973
MAX_REQUEST_BYTES = 8192
TRANSPORT_SCHEMA_VERSION = "phios.ghostwalk-control-transport.v0.26"
TRANSPORT_IDENTITY = "phios-ghostwalk-control"
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

    def _read_json(self) -> object:
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
        if length < 1 or length > MAX_REQUEST_BYTES:
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
        stop_callback: Callable[[], object] | None = None,
    ) -> None:
        if address[0] != LOOPBACK_HOST:
            raise GhostWalkControlBridgeError(
                "Ghost-Walk control server must bind IPv4 loopback"
            )
        self.surface = surface
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
    server = GhostWalkControlServer(
        (LOOPBACK_HOST, args.port),
        surface=surface,
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
