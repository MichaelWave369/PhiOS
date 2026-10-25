"""Opt-in PhiARK local gateway R0.7. Never installs, grants, or launches an app.

This is a bounded diagnostic bridge between an already-running, private PhiARK
Unix socket and a browser on 127.0.0.1. It is not a PhiOS runtime authority or
evidence of Bubblewrap isolation or source-commit attestation.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import secrets
import socket
import stat
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "phios.phiark_gateway_plan.v0.1"
SESSION_COOKIE = "phios_phiark_session"
_MAX_BODY = 128
_MAX_PATH = 2048
_MAX_RESPONSE = 512 * 1024 * 1024 + 4096
_DOC_RE = re.compile(r"^/documents/[a-f0-9]{64}$")
_ROUTES = frozenset(("/", "/app.js", "/style.css", "/api/status", "/api/items", "/api/kiwix", "/api/search"))
_SCRIPT = (
    "(async()=>{const t=location.hash.slice(1);"
    "history.replaceState(null,'','/_phiark/activate');"
    "if(!t){document.body.textContent='Missing operator token';return;}"
    "try{const r=await fetch('/_phiark/activate',{method:'POST',"
    "headers:{'Content-Type':'text/plain'},body:t,credentials:'same-origin'});"
    "if(!r.ok)throw Error('denied');location.replace('/');}"
    "catch{document.body.textContent='Activation denied';}})();"
)
_SCRIPT_SHA = base64.b64encode(hashlib.sha256(_SCRIPT.encode()).digest()).decode()
_ACTIVATOR = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='referrer' content='no-referrer'><title>PhiARK local access</title>"
    "</head><body>Activating approved local PhiARK browser session..."
    "<script>" + _SCRIPT + "</script></body></html>"
).encode()


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_root(data_root: str | Path) -> Path:
    raw = Path(data_root).expanduser()
    if not raw.is_absolute():
        raise ValueError("absolute PHIARK_DATA_DIR required")
    # No resolve() before inspecting components: symlinks cannot redirect roots.
    root = Path(os.path.abspath(raw))
    for item in (root, *root.parents):
        info = item.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError("unsafe data directory component")
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("data root must belong to current user with private permissions")
    return root


def inspect_gateway(data_root: str | Path, port: int = 3692) -> dict[str, Any]:
    if sys.platform != "linux":
        raise ValueError("PhiARK Unix-socket gateway is Linux-only")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("explicit nonprivileged loopback port required")
    root = _safe_root(data_root)
    path = root / ".phiark.sock"
    sock = path.lstat()
    if not stat.S_ISSOCK(sock.st_mode) or sock.st_uid != os.getuid() or sock.st_mode & 0o077:
        raise ValueError("private owner-only PhiARK socket required")
    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "app_id": "phi.phiark",
        "data_root": str(root),
        "socket_path": str(path),
        "socket_device": sock.st_dev,
        "socket_inode": sock.st_ino,
        "host": "127.0.0.1",
        "port": port,
        "status": "READY_FOR_OPERATOR_REVIEW",
        "source_commit_attested": False,
        "socket_process_identity_attested": False,
        "phios_installed": False,
        "install_authority": False,
        "launch_authority": False,
        "host_network_bridge_authorized": False,
        "external_network_access": False,
    }
    plan["plan_sha256"] = hashlib.sha256(_canonical(plan).encode()).hexdigest()
    return plan


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__("local.phiark", timeout=5)
        self.socket_path = socket_path

    def connect(self) -> None:
        link = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        link.settimeout(5)
        try:
            link.connect(self.socket_path)
        except BaseException:
            link.close()
            raise
        self.sock = link


def _probe(plan: dict[str, Any]) -> None:
    conn = _UnixHTTPConnection(plan["socket_path"])
    try:
        conn.request("GET", "/api/status", headers={"Accept": "application/json"})
        res = conn.getresponse()
        if res.status != 200:
            raise ValueError("PhiARK private socket did not return HTTP 200")
        raw = res.read(8193)
        if len(raw) > 8192:
            raise ValueError("PhiARK status payload too large")
        value = json.loads(raw)
        if (
            not isinstance(value, dict) or value.get("mode") != "LOCAL"
            or value.get("networkRequired") is not False
            or type(value.get("documents")) is not int or value["documents"] < 0
        ):
            raise ValueError("PhiARK private status contract mismatch")
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        raise ValueError("PhiARK private socket readiness check failed") from exc
    finally:
        conn.close()


class PhiARKGateway(HTTPServer):
    allow_reuse_address = False

    def __init__(self, plan: dict[str, Any], approved_plan_sha256: str):
        if not secrets.compare_digest(plan["plan_sha256"], approved_plan_sha256):
            raise ValueError("operator-approved gateway plan SHA-256 mismatch")
        current = inspect_gateway(plan["data_root"], plan["port"])
        if current["plan_sha256"] != plan["plan_sha256"]:
            raise ValueError("gateway plan or private socket changed since approval")
        _probe(current)
        self.plan = current
        self.activation_token = secrets.token_urlsafe(32)
        self.session_token = secrets.token_urlsafe(32)
        self.activation_used = False
        super().__init__(("127.0.0.1", current["port"]), _Handler)

    @property
    def operator_url(self) -> str:
        # Browser fragment is not sent in the HTTP request line or Referer.
        return (
            "http://127.0.0.1:" + str(self.plan["port"])
            + "/_phiark/activate#" + self.activation_token
        )


class _Handler(BaseHTTPRequestHandler):
    server: PhiARKGateway
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # No access logs: never persist capability tokens, URLs or private doc IDs.
        pass

    def _headers(self, status: int, content_type: str, length: int, *, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self' 'sha256-" + _SCRIPT_SHA
            + "'; style-src 'self'; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'",
        )
        if extra:
            for name, value in extra.items():
                self.send_header(name, value)
        self.end_headers()

    def _answer(self, status: int, msg: str, *, head: bool = False) -> None:
        raw = msg.encode()
        self._headers(status, "text/plain; charset=utf-8", len(raw))
        if not head:
            self.wfile.write(raw)

    def _context_allowed(self) -> bool:
        expected = "127.0.0.1:" + str(self.server.plan["port"])
        if self.headers.get("Host") != expected:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + expected:
            return False
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site not in (None, "same-origin", "none"):
            return False
        referer = self.headers.get("Referer")
        if referer is not None and not referer.startswith("http://" + expected + "/"):
            return False
        return True

    def _authorized(self) -> bool:
        try:
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            value = cookie.get(SESSION_COOKIE)
            return bool(value and secrets.compare_digest(value.value, self.server.session_token))
        except (ValueError, KeyError):
            return False

    def _route(self) -> str | None:
        if len(self.path) > _MAX_PATH:
            return None
        target = urlsplit(self.path)
        if target.scheme or target.netloc or target.fragment:
            return None
        if target.path not in _ROUTES and not _DOC_RE.fullmatch(target.path):
            return None
        if target.query and target.path != "/api/search":
            return None
        return self.path

    def _socket_unchanged(self) -> bool:
        try:
            current = inspect_gateway(self.server.plan["data_root"], self.server.plan["port"])
            return current["plan_sha256"] == self.server.plan["plan_sha256"]
        except (OSError, ValueError):
            return False

    def _serve(self, *, head: bool = False) -> None:
        if not self._context_allowed():
            return self._answer(403, "Local origin required", head=head)
        if self.path == "/_phiark/activate" and not head:
            self._headers(200, "text/html; charset=utf-8", len(_ACTIVATOR))
            self.wfile.write(_ACTIVATOR)
            return
        if not self._authorized():
            return self._answer(403, "Approved local session required", head=head)
        route = self._route()
        if route is None:
            return self._answer(404, "Not found", head=head)
        if not self._socket_unchanged():
            return self._answer(503, "Private socket changed", head=head)
        conn = _UnixHTTPConnection(self.server.plan["socket_path"])
        headers_sent = False
        try:
            conn.request("HEAD" if head else "GET", route, headers={"Accept": "*/*"})
            response = conn.getresponse()
            length = response.getheader("Content-Length")
            declared = int(length) if length is not None else None
            if declared is not None and not 0 <= declared <= _MAX_RESPONSE:
                raise ValueError("invalid upstream response length")
            content_type = response.getheader("Content-Type", "application/octet-stream")
            if "\r" in content_type or "\n" in content_type or len(content_type) > 128:
                raise ValueError("invalid upstream content type")
            forwarded = {}
            disposition = response.getheader("Content-Disposition")
            if disposition is not None and len(disposition) <= 160 and "\r" not in disposition and "\n" not in disposition:
                forwarded["Content-Disposition"] = disposition
            # HTTP/1.0 close-delimited for content without an upstream length.
            self.send_response(response.status)
            self.send_header("Content-Type", content_type)
            if declared is not None:
                self.send_header("Content-Length", str(declared))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            for key, value in forwarded.items():
                self.send_header(key, value)
            self.end_headers()
            headers_sent = True
            if not head:
                read_total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    read_total += len(chunk)
                    if read_total > _MAX_RESPONSE:
                        self.close_connection = True
                        break
                    self.wfile.write(chunk)
        except (ValueError, OSError, http.client.HTTPException):
            if not headers_sent:
                # Fail closed before emitting status headers; no arbitrary upstream.
                self._answer(502, "Private upstream unavailable", head=head)
            else:
                self.close_connection = True
        finally:
            conn.close()

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve(head=True)

    def do_POST(self) -> None:
        if not self._context_allowed():
            return self._answer(403, "Local origin required")
        if self.path != "/_phiark/activate":
            return self._answer(405, "Only local activation accepts POST")
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self._answer(400, "Invalid activation length")
        if not 1 <= size <= _MAX_BODY or self.headers.get("Content-Type") != "text/plain":
            return self._answer(400, "Invalid activation body")
        candidate = self.rfile.read(size).decode("ascii", errors="replace")
        if self.server.activation_used or not secrets.compare_digest(candidate, self.server.activation_token):
            return self._answer(403, "Activation denied")
        self.server.activation_used = True
        self.server.activation_token = ""
        self._headers(
            204, "text/plain; charset=utf-8", 0,
            extra={
                "Set-Cookie": SESSION_COOKIE + "=" + self.server.session_token
                + "; Path=/; Max-Age=3600; HttpOnly; SameSite=Strict",
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phi-phiark-gateway")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "serve"):
        sub = commands.add_parser(action)
        sub.add_argument("--data-root", type=Path, required=True)
        sub.add_argument("--port", type=int, default=3692)
        if action == "serve":
            sub.add_argument("--approve-plan-sha", required=True)
    args = parser.parse_args(argv)
    try:
        plan = inspect_gateway(args.data_root, args.port)
        if args.action == "plan":
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        with PhiARKGateway(plan, args.approve_plan_sha) as server:
            print("One-time local browser URL: " + server.operator_url, flush=True)
            print("Read-only bridge; NOT PhiOS install/launch authority. Ctrl+C to stop.", flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
        return 0
    except (OSError, ValueError) as exc:
        print("PhiARK gateway blocked: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
