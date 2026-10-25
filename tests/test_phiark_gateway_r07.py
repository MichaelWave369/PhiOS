"""R0.7 local gateway contract: synthetic Unix backend, not a PhiOS installation."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import socketserver
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from phios.apps.phiark_gateway import PhiARKGateway, inspect_gateway

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only Unix socket")


class _PhiARKFixture(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/api/status":
            content = json.dumps({"mode": "LOCAL", "networkRequired": False,
                                  "documents": 1, "verified": False}).encode()
        elif self.path == "/api/search?q=offline":
            content = b'[{"title":"Offline guide"}]'
        elif self.path == "/":
            content = b"<html><body>PhiARK</body></html>"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if self.path.startswith("/api/") else "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


@pytest.fixture
def fixture(tmp_path: Path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    socket_path = root / ".phiark.sock"

    class _Backend(socketserver.UnixStreamServer):
        allow_reuse_address = False

    backend = _Backend(str(socket_path), _PhiARKFixture)
    socket_path.chmod(0o600)
    worker = threading.Thread(target=backend.serve_forever, daemon=True)
    worker.start()
    try:
        yield root, socket_path, backend
    finally:
        backend.shutdown()
        backend.server_close()
        worker.join(timeout=3)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(port: int, path: str, method: str = "GET", *,
             headers: dict[str, str] | None = None, body: str | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        content = response.read()
        return response.status, dict(response.getheaders()), content
    finally:
        connection.close()


def test_plan_is_read_only_and_evidence_is_not_authority(fixture) -> None:
    root, sock, _ = fixture
    plan = inspect_gateway(root, 3692)
    assert plan["socket_path"] == str(sock)
    assert plan["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert plan["host"] == "127.0.0.1"
    assert plan["source_commit_attested"] is False
    assert plan["socket_process_identity_attested"] is False
    assert plan["phios_installed"] is False
    assert plan["install_authority"] is False
    assert plan["launch_authority"] is False
    assert plan["host_network_bridge_authorized"] is False
    with pytest.raises(ValueError, match="mismatch"):
        PhiARKGateway(plan, "0" * 64)


def test_explicit_approved_gateway_with_browser_activation(fixture) -> None:
    root, _, _ = fixture
    port = _free_port()
    plan = inspect_gateway(root, port)
    with PhiARKGateway(plan, plan["plan_sha256"]) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, _, _ = _request(port, "/api/status")
            assert status == 403  # Never proxy before operator session activation.
            status, headers, page = _request(port, "/_phiark/activate")
            assert status == 200 and b"Activating approved" in page
            assert "no-store" in headers["Cache-Control"]

            token = server.operator_url.rsplit("#", 1)[1]
            # A foreign Origin cannot activate even if it somehow knows the token.
            status, _, _ = _request(
                port, "/_phiark/activate", "POST",
                headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
                body=token,
            )
            assert status == 403
            status, headers, _ = _request(
                port, "/_phiark/activate", "POST",
                headers={"Content-Type": "text/plain"}, body=token,
            )
            assert status == 204
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
            status, _, _ = _request(
                port, "/_phiark/activate", "POST",
                headers={"Content-Type": "text/plain"}, body=token,
            )
            assert status == 403  # One-time activation.
            status, _, data = _request(port, "/api/status", headers={"Cookie": cookie})
            assert status == 200
            assert json.loads(data)["mode"] == "LOCAL"
            status, _, data = _request(port, "/api/search?q=offline", headers={"Cookie": cookie})
            assert status == 200 and b"Offline guide" in data
            status, _, _ = _request(port, "/documents/bad", headers={"Cookie": cookie})
            assert status == 404
            status, _, _ = _request(port, "/api/status", headers={
                "Cookie": cookie, "Origin": "http://attacker.invalid",
            })
            assert status == 403
            status, _, _ = _request(port, "/api/status", headers={
                "Cookie": cookie, "Sec-Fetch-Site": "cross-site",
            })
            assert status == 403
            status, _, _ = _request(port, "/api/status", headers={
                "Cookie": cookie, "Host": "fake.example",
            })
            assert status == 403
            status, _, _ = _request(port, "/api/status", "POST", headers={"Cookie": cookie})
            assert status == 405
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_socket_path_replacement_blocks_proxy(fixture) -> None:
    root, socket_path, _ = fixture
    port = _free_port()
    plan = inspect_gateway(root, port)
    with PhiARKGateway(plan, plan["plan_sha256"]) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = server.operator_url.rsplit("#", 1)[1]
            _, headers, _ = _request(
                port, "/_phiark/activate", "POST",
                headers={"Content-Type": "text/plain"}, body=token,
            )
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            socket_path.unlink()  # Synthetic local threat only, never production recovery.
            status, _, _ = _request(port, "/api/status", headers={"Cookie": cookie})
            assert status == 503
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_untrusted_root_and_socket_are_rejected(fixture, tmp_path: Path) -> None:
    root, socket_path, _ = fixture
    root.chmod(0o755)
    with pytest.raises(ValueError, match="private permissions"):
        inspect_gateway(root)
    root.chmod(0o700)
    socket_path.chmod(0o666)
    with pytest.raises(ValueError, match="owner-only"):
        inspect_gateway(root)
    socket_path.chmod(0o600)
    alias = tmp_path / "linked-private"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe data directory"):
        inspect_gateway(alias)
    with pytest.raises(ValueError, match="port"):
        inspect_gateway(root, 80)
