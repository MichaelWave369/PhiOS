"""Read-only loopback projection for the canonical Curiosity Store.

The service deliberately does not accept browser-originated persistence.
POST /api/v1/curiosity/artifacts fails closed with action_lease_required until
there is a trusted local lease issuer/verifier bridge.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from phios.curiosity_store import CuriosityStore

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_CURIOSITY_PORT = 3971
MAX_ARTIFACTS = 64


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_curiosity_projection(
    store: CuriosityStore,
    *,
    limit: int = 32,
) -> dict[str, object]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= MAX_ARTIFACTS:
        raise ValueError(
            f"limit must be between 1 and {MAX_ARTIFACTS}"
        )

    all_artifacts = store.artifacts()
    selected = list(reversed(all_artifacts[-limit:]))
    selected_hashes = {
        artifact.curiosity_artifact_sha256
        for artifact in selected
    }
    pointers = [
        pointer.to_dict()
        for pointer in reversed(store.return_pointers())
        if pointer.artifact_sha256 in selected_hashes
    ]

    return {
        "schemaVersion": "phios.curiosity-projection.v0.4",
        "source": "canonical-curiosity-store",
        "generatedAt": _utc_now(),
        "persistent": True,
        "writeAvailable": False,
        "writeHoldReason": "action_lease_broker_unavailable",
        "limit": limit,
        "count": len(selected),
        "omittedArtifactCount": max(
            0,
            len(all_artifacts) - len(selected),
        ),
        "artifacts": [
            artifact.to_dict()
            for artifact in selected
        ],
        "returnPointers": pointers,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": False,
    }


def projection_envelope(
    store: CuriosityStore,
    *,
    limit: int = 32,
) -> dict[str, object]:
    return {
        "transportSchemaVersion": "phios.curiosity-transport.v0.4",
        "transport": "loopback-http",
        "transportIdentity": "phios-curiosity-store-reader",
        "localOnly": True,
        "readOnly": True,
        "operationalAuthority": False,
        "actionAuthority": False,
        "executionAuthority": False,
        "effectPerformed": False,
        "servedAt": _utc_now(),
        "projection": build_curiosity_projection(
            store,
            limit=limit,
        ),
    }


class CuriosityProjectionHandler(BaseHTTPRequestHandler):
    server: "CuriosityProjectionServer"

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
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

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/v1/curiosity":
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "readOnly": True,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
            )
            return

        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
        if set(query) - {"limit"}:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_query",
                    "readOnly": True,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
            )
            return
        raw_limit = query.get("limit", ["32"])
        if len(raw_limit) != 1:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_limit",
                    "readOnly": True,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
            )
            return
        try:
            limit = int(raw_limit[0])
            body = projection_envelope(
                self.server.store,
                limit=limit,
            )
        except (TypeError, ValueError):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_limit",
                    "readOnly": True,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
            )
            return
        self._json(HTTPStatus.OK, body)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/curiosity/artifacts":
            self._json(
                HTTPStatus.PRECONDITION_REQUIRED,
                {
                    "error": "action_lease_required",
                    "reason": (
                        "browser persistence is held until a trusted "
                        "ActionLease issuer/verifier bridge is configured"
                    ),
                    "localOnly": True,
                    "writeAvailable": False,
                    "operationalAuthority": False,
                    "actionAuthority": False,
                    "executionAuthority": False,
                    "effectPerformed": False,
                },
            )
            return
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {
                "error": "method_not_allowed",
                "executionAuthority": False,
                "effectPerformed": False,
            },
        )


class CuriosityProjectionServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        store: CuriosityStore,
    ) -> None:
        if address[0] != LOOPBACK_HOST:
            raise ValueError(
                "Curiosity projection server must bind IPv4 loopback"
            )
        self.store = store
        super().__init__(address, CuriosityProjectionHandler)


def _default_store_root() -> Path:
    configured = os.environ.get("PHIOS_CURIOSITY_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".phios" / "curiosity"


def _default_port() -> int:
    raw = os.environ.get("PHIOS_CURIOSITY_PORT")
    if raw is None:
        return DEFAULT_CURIOSITY_PORT
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise ValueError(
            "PHIOS_CURIOSITY_PORT must be from 1024 to 65535"
        )
    return port


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port(),
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=_default_store_root(),
    )
    args = parser.parse_args()

    if not 1024 <= args.port <= 65535:
        raise SystemExit("port must be from 1024 to 65535")

    store = CuriosityStore(args.store_root)
    server = CuriosityProjectionServer(
        (LOOPBACK_HOST, args.port),
        store,
    )
    try:
        print(
            "PhiOS Curiosity projection: "
            f"http://{LOOPBACK_HOST}:{args.port}"
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
