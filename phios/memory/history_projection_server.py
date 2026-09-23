from __future__ import annotations

import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .operator import MemoryOperatorRuntime
from .system_history import (
    SYSTEM_HISTORY_PROJECTION_LIMIT,
    SystemHistoryProjectionService,
)
from .system_history_comparison import SystemHistoryComparisonService

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_HISTORY_PORT = 3970
TRANSPORT_SCHEMA = "phios.system-history-transport.v0.12"
TRANSPORT_IDENTITY = "phios-governed-history-reader"
COMPARISON_TRANSPORT_SCHEMA = "phios.system-history-comparison-transport.v0.13"


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _envelope(projection: dict[str, object]) -> dict[str, object]:
    return {
        "transportSchemaVersion": TRANSPORT_SCHEMA,
        "transport": "loopback-http",
        "transportIdentity": TRANSPORT_IDENTITY,
        "localOnly": True,
        "readOnly": True,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": False,
        "servedAt": datetime.now(UTC).isoformat(),
        "projection": projection,
    }


def _comparison_envelope(comparison: dict[str, object]) -> dict[str, object]:
    return {
        "transportSchemaVersion": COMPARISON_TRANSPORT_SCHEMA,
        "transport": "loopback-http",
        "transportIdentity": TRANSPORT_IDENTITY,
        "localOnly": True,
        "readOnly": True,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": False,
        "servedAt": datetime.now(UTC).isoformat(),
        "comparison": comparison,
    }


def create_history_projection_server(
    runtime: MemoryOperatorRuntime,
    *,
    port: int = DEFAULT_HISTORY_PORT,
) -> ThreadingHTTPServer:
    runtime.require_enabled()
    if not runtime.authority.allows("history.read"):
        raise PermissionError("history projection sidecar requires explicit history.read authority")
    if not runtime.authority.allows("memory.read"):
        raise PermissionError("history projection sidecar requires explicit memory.read authority")
    if isinstance(port, bool) or not isinstance(port, int) or not (port == 0 or 1024 <= port <= 65535):
        raise ValueError("history projection port must be 0 or between 1024 and 65535")

    projection_service = SystemHistoryProjectionService(runtime)
    comparison_service = SystemHistoryComparisonService(runtime)

    class Handler(BaseHTTPRequestHandler):
        server_version = "PhiOSHistoryProjection/0.13"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _headers(self, status: int, *, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()

        def _write_json(self, status: int, payload: object) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            url = urlsplit(self.path)
            if url.path == "/api/v1/health":
                if url.query:
                    self._write_json(400, {"error": "health route does not accept query parameters"})
                    return
                self._write_json(
                    200,
                    {
                        "status": "ok",
                        "transportIdentity": TRANSPORT_IDENTITY,
                        "localOnly": True,
                        "readOnly": True,
                        "executionAuthority": False,
                        "effectPerformed": False,
                    },
                )
                return

            if url.path == "/api/v1/system-history-compare":
                query = parse_qs(url.query, keep_blank_values=True)
                if (
                    set(query) != {"from", "to"}
                    or any(len(values) != 1 for values in query.values())
                ):
                    self._write_json(
                        400,
                        {"error": "comparison requires one from and one to record id"},
                    )
                    return
                try:
                    comparison = comparison_service.compare(
                        from_record_id=query["from"][0],
                        to_record_id=query["to"][0],
                    ).to_dict()
                except ValueError as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                except PermissionError as exc:
                    self._write_json(403, {"error": str(exc)})
                    return
                except LookupError as exc:
                    self._write_json(404, {"error": str(exc)})
                    return

                self._write_json(200, _comparison_envelope(comparison))
                return

            if url.path != "/api/v1/system-history":
                self._write_json(404, {"error": "not found"})
                return

            query = parse_qs(url.query, keep_blank_values=True)
            if set(query) - {"limit"} or any(len(values) != 1 for values in query.values()):
                self._write_json(400, {"error": "unsupported history query"})
                return
            try:
                limit = (
                    int(query["limit"][0])
                    if "limit" in query
                    else SYSTEM_HISTORY_PROJECTION_LIMIT
                )
                projection = projection_service.project(limit=limit).to_dict()
            except ValueError as exc:
                self._write_json(400, {"error": str(exc)})
                return
            except PermissionError as exc:
                self._write_json(403, {"error": str(exc)})
                return

            self._write_json(200, _envelope(projection))

        def _method_not_allowed(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(
                _json_bytes(
                    {
                        "error": "method not allowed",
                        "readOnly": True,
                        "executionAuthority": False,
                        "effectPerformed": False,
                    }
                )
            )

        def do_POST(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_PUT(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_PATCH(self) -> None:  # noqa: N802
            self._method_not_allowed()

        def do_DELETE(self) -> None:  # noqa: N802
            self._method_not_allowed()

    return ThreadingHTTPServer((LOOPBACK_HOST, port), Handler)


def serve_system_history(
    runtime: MemoryOperatorRuntime,
    *,
    port: int = DEFAULT_HISTORY_PORT,
) -> None:
    server = create_history_projection_server(runtime, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
