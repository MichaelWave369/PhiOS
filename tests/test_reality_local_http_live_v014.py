import hashlib
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from phios.mandala import MandalaStatus
from phios.reality import (
    LocalHttpObservationError,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
)
from phios.spine.runtime import PhiOSSpine


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    target_hits = 0

    def do_GET(self) -> None:
        if self.path == "/ok":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "session=must-not-be-recorded")
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/target")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self.path == "/target":
            type(self).target_hits += 1
            body = b"followed"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/large":
            body = b"abcdefghij"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_server() -> Iterator[tuple[str, int]]:
    _Handler.target_hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_stdlib_loopback_provider_observes_exact_response() -> None:
    provider = StdlibLoopbackHttpStateProvider()

    with _loopback_server() as (host, port):
        observation = provider.observe(
            url=f"http://{host}:{port}/ok",
            timeout_seconds=2.0,
            max_body_bytes=65_536,
        )

    body = b'{"ok":true}'
    assert observation.method == "GET"
    assert observation.status_code == 200
    assert observation.body_sha256 == hashlib.sha256(body).hexdigest()
    assert observation.body_bytes_observed == len(body)
    assert observation.body_truncated is False
    assert observation.body_digest_scope == "full"
    assert observation.redirect_followed is False
    assert observation.headers["content-type"] == "application/json"
    assert observation.headers["content-length"] == str(len(body))
    assert "set-cookie" not in observation.headers
    assert "server" not in observation.headers


def test_stdlib_loopback_provider_does_not_follow_redirects() -> None:
    provider = StdlibLoopbackHttpStateProvider()

    with _loopback_server() as (host, port):
        observation = provider.observe(
            url=f"http://{host}:{port}/redirect",
            timeout_seconds=2.0,
            max_body_bytes=1024,
        )
        target_hits = _Handler.target_hits

    assert observation.status_code == 302
    assert observation.redirect_followed is False
    assert target_hits == 0
    assert "location" not in observation.headers


def test_stdlib_loopback_provider_hashes_only_bounded_prefix_when_truncated() -> None:
    provider = StdlibLoopbackHttpStateProvider()

    with _loopback_server() as (host, port):
        observation = provider.observe(
            url=f"http://{host}:{port}/large",
            timeout_seconds=2.0,
            max_body_bytes=4,
        )

    assert observation.body_bytes_observed == 4
    assert observation.body_truncated is True
    assert observation.body_digest_scope == "prefix"
    assert observation.body_sha256 == hashlib.sha256(b"abcd").hexdigest()


def test_stdlib_loopback_provider_rejects_mixed_non_loopback_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = StdlibLoopbackHttpStateProvider()

    def fake_getaddrinfo(
        host: str,
        port: int,
        *,
        type: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        assert host == "localhost"
        assert port == 8000
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(LocalHttpObservationError) as exc_info:
        provider.observe(
            url="http://localhost:8000/health",
            timeout_seconds=2.0,
            max_body_bytes=1024,
        )

    assert exc_info.value.code == "local_http_resolution_not_loopback"


def test_live_loopback_observation_flows_through_reality_receipt(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-live-v014",
    )

    with _loopback_server() as (host, port):
        url = f"http://{host}:{port}/ok"
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE,
            statement="The bounded local endpoint returned HTTP 200.",
            http_url=url,
            expected_http_status=200,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["observed_http_status"] == 200
    assert claim_result["provider"] == "stdlib-loopback-http"
    assert claim_result["body_truncated"] is False
    assert claim_result["observation_evidence_ref"] in result.receipt.evidence_used
    assert "http_status_is_not_application_health" in result.receipt.limitations
