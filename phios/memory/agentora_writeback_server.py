"""Explicitly enabled, authenticated localhost-only Agentora R4b memory endpoint.

No listener is activated on import or by default PhiOS configuration.
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from phios.spine.api_keys import ApiKeyBoundary, InboundApiKeySpec

from .agentora_writeback import AgentoraWritebackAdmission, PROTOCOL
from .operator import MemoryOperatorRuntime

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_WRITEBACK_PORT = 8090
WRITEBACK_ROUTE = "/api/v1/agentora/writeback"
MAX_REQUEST_BYTES = 48 * 1024
KEY_ENV = "PHIOS_AGENTORA_WRITEBACK_KEY"
_KEY_ID = "agentora-writeback-r4b"
_AUDIENCE = "phios.memory.agentora.writeback"


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("non-finite JSON number")


def create_agentora_writeback_server(
    runtime: MemoryOperatorRuntime,
    *,
    token: str,
    port: int = DEFAULT_WRITEBACK_PORT,
) -> ThreadingHTTPServer:
    """Build a dormant loopback listener with existing governed API key verification."""
    runtime.require_enabled()
    for permission in ("memory.read", "memory.write"):
        if not runtime.authority.allows(permission):
            raise PermissionError("Agentora bridge requires " + permission)
    if not isinstance(token, str) or len(token) < 32 or token != token.strip():
        raise ValueError("Agentora bridge requires a 32+ character secret")
    if "\n" in token or "\r" in token:
        raise ValueError("invalid Agentora bridge secret")
    if isinstance(port, bool) or not isinstance(port, int) or not (
        port == 0 or 1024 <= port <= 65535
    ):
        raise ValueError("Agentora bridge port must be 0 or between 1024 and 65535")

    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id=_KEY_ID,
            audience=_AUDIENCE,
            secret=token,
            scopes=("memory.read", "memory.write"),
        )
    )
    admission = AgentoraWritebackAdmission(runtime)

    class Handler(BaseHTTPRequestHandler):
        server_version = "PhiOSAgentoraWriteback/0.1"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            del format, args  # Never log credentials, mission contents, or operation IDs.

        def _reply(self, status: int, result: dict[str, object]) -> None:
            body = json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            keys = self.headers.get_all("X-API-Key", [])
            if len(keys) != 1:
                self._reply(401, {"ok": False, "error_code": "UNAUTHENTICATED"})
                return False
            receipt = boundary.authenticate_inbound(
                key_id=_KEY_ID, presented_key=keys[0], audience=_AUDIENCE
            )
            if not receipt.authenticated:
                self._reply(401, {"ok": False, "error_code": "UNAUTHENTICATED"})
                return False
            return True

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if self.path != WRITEBACK_ROUTE:
                self._reply(404, {"ok": False, "error_code": "NOT_FOUND"})
                return
            if self.headers.get("Transfer-Encoding") is not None:
                self._reply(400, {"ok": False, "error_code": "UNSUPPORTED_ENCODING"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != (
                "application/json"
            ):
                self._reply(415, {"ok": False, "error_code": "JSON_REQUIRED"})
                return
            sizes = self.headers.get_all("Content-Length", [])
            if len(sizes) != 1 or not sizes[0].isdigit():
                self._reply(411, {"ok": False, "error_code": "LENGTH_REQUIRED"})
                return
            size = int(sizes[0])
            if not 0 < size <= MAX_REQUEST_BYTES:
                self._reply(413, {"ok": False, "error_code": "REQUEST_TOO_LARGE"})
                return
            try:
                raw = self.rfile.read(size)
                request: Any = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique_pairs,
                    parse_constant=_reject_constant,
                )
                if not isinstance(request, dict):
                    raise ValueError("envelope must be a JSON object")
                if set(request) != {
                    "protocol_version", "payload", "created_at_utc", "operation_id"
                } or request.get("protocol_version") != PROTOCOL:
                    raise ValueError("unsupported writeback envelope")
                operation = request["operation_id"]
                if not isinstance(operation, str) or not re.fullmatch(
                    r"[0-9a-f]{64}", operation
                ):
                    raise ValueError("operation ID must be lowercase SHA-256")
                payload = request["payload"]
                created = request["created_at_utc"]
                if not isinstance(payload, dict) or not isinstance(created, str):
                    raise ValueError("payload and created_at_utc are required")
                receipt = admission.admit(
                    payload, created_at_utc=created, expected_operation_id=operation
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                conflict = "different request" in str(exc)
                self._reply(409 if conflict else 400, {
                    "ok": False,
                    "error_code": "IDENTITY_CONFLICT" if conflict else "INVALID_REQUEST",
                })
                return
            except PermissionError:
                self._reply(403, {"ok": False, "error_code": "MEMORY_DENIED"})
                return
            except (OSError, RuntimeError):
                self._reply(503, {"ok": False, "error_code": "MEMORY_UNAVAILABLE"})
                return
            if receipt.get("state") == "published":
                self._reply(200, receipt)
            elif receipt.get("state") == "pending":
                self._reply(202, receipt)
            else:
                self._reply(503, {
                    "ok": False, "error_code": "MEMORY_UNAVAILABLE",
                    "operation_id": operation,
                })

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            parsed = urlsplit(self.path)
            prefix = WRITEBACK_ROUTE + "/"
            if parsed.query or parsed.path != self.path or not parsed.path.startswith(prefix):
                self._reply(404, {"ok": False, "error_code": "NOT_FOUND"})
                return
            op_id = parsed.path[len(prefix):]
            if not re.fullmatch(r"[0-9a-f]{64}", op_id):
                self._reply(400, {"ok": False, "error_code": "INVALID_OPERATION_ID"})
                return
            try:
                result = admission.status(op_id)
            except PermissionError:
                self._reply(403, {"ok": False, "error_code": "MEMORY_DENIED"})
                return
            except (OSError, RuntimeError):
                self._reply(503, {"ok": False, "error_code": "MEMORY_UNAVAILABLE"})
                return
            self._reply(
                404 if result["state"] == "not_found"
                else 200 if result["state"] == "published" else 202,
                result,
            )

        def do_PUT(self) -> None:  # noqa: N802
            self._reply(405, {"ok": False, "error_code": "METHOD_NOT_ALLOWED"})

        def do_PATCH(self) -> None:  # noqa: N802
            self._reply(405, {"ok": False, "error_code": "METHOD_NOT_ALLOWED"})

        def do_DELETE(self) -> None:  # noqa: N802
            self._reply(405, {"ok": False, "error_code": "METHOD_NOT_ALLOWED"})

    server = ThreadingHTTPServer((LOOPBACK_HOST, port), Handler)
    server.daemon_threads = True
    return server


def serve_agentora_writeback(
    runtime: MemoryOperatorRuntime, *, port: int = DEFAULT_WRITEBACK_PORT
) -> None:
    server = create_agentora_writeback_server(
        runtime, token=os.environ.get(KEY_ENV, ""), port=port
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
