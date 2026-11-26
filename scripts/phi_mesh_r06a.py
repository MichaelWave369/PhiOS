"""R06-A: explicit, certificate-pinned LAN challenge; no remote task authority."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import ssl
import sys

from phios.network.homenode import HomeNodeConfig, HomeNodeTrustError, load_trust

SCHEMA = "phios.mesh.challenge.v1"
PORT = 3769
MAX_BODY = 2048
HEX = re.compile(r"[0-9a-f]{64}\Z")
NODE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}\Z")


def lan_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return any(ip in ipaddress.IPv4Network(net) for net in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.1/32"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate field")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique)


def challenge(nonce, node):
    if not isinstance(nonce, str) or not HEX.fullmatch(nonce) or not NODE.fullmatch(node):
        raise ValueError("challenge fields")
    # Fixed synthetic computation; no input-controlled iteration count or command.
    value = bytes.fromhex(nonce)
    for _ in range(369):
        value = hashlib.sha256(value).digest()
    return {"schema": SCHEMA, "nonce": nonce, "node": node,
            "result_sha256": value.hex(), "rounds": 369,
            "state": "CHALLENGE_ONLY", "execution_authority": False,
            "inference_verified": False, "offline_verified": False}


def private_file(path, limit):
    path = Path(path)
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or any((p / ".git").exists() for p in path.parents)):
        raise ValueError("private absolute file required outside Git")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise ValueError("file size")
    return data


def token_from_file(path):
    token = private_file(path, 128).decode("ascii").rstrip("\r\n")
    if not HEX.fullmatch(token):
        raise ValueError("64 lowercase hex token required")
    return token


class MeshServer(HTTPServer):
    allow_reuse_address = False

    def __init__(self, ip, peer, node, context, token, port=PORT):
        if not lan_ip(ip) or not lan_ip(peer) or not NODE.fullmatch(node):
            raise ValueError("explicit LAN addresses and node required")
        if not HEX.fullmatch(token):
            raise ValueError("token format")
        self.peer = peer
        self.node = node
        self.context = context
        self.token = token
        self.timeout = 60
        super().__init__((ip, port), Handler)

    def get_request(self):
        sock, address = super().get_request()
        try:
            if address[0] != self.peer:
                raise OSError("peer refused")
            sock.settimeout(5)
            return self.context.wrap_socket(sock, server_side=True), address
        except BaseException:
            sock.close()
            raise

    def handle_error(self, request, client_address):
        # Avoid leaking paths, tokens, addresses or arbitrary client content.
        return


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def respond(self, status, body):
        data = canonical(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        server = self.server
        expected_host = "%s:%d" % server.server_address
        if (self.path != "/v1/challenge" or self.headers.get_all("Host") != [expected_host]
                or "Origin" in self.headers or "Transfer-Encoding" in self.headers):
            self.respond(403, {"state": "REFUSED"})
            return
        auth = self.headers.get_all("Authorization") or []
        if (len(auth) != 1 or not re.fullmatch(r"Bearer [0-9a-f]{64}", auth[0])
                or not hmac.compare_digest(auth[0], "Bearer " + server.token)):
            self.respond(403, {"state": "REFUSED"})
            return
        sizes = self.headers.get_all("Content-Length") or []
        if (len(sizes) != 1 or not re.fullmatch(r"[0-9]{1,4}", sizes[0])
                or not 0 < int(sizes[0]) <= MAX_BODY
                or self.headers.get_all("Content-Type") != ["application/json"]):
            self.respond(400, {"state": "REFUSED"})
            return
        try:
            packet = decode(self.rfile.read(int(sizes[0])))
            if (type(packet) is not dict or set(packet) != {"schema", "nonce"}
                    or packet["schema"] != SCHEMA):
                raise ValueError("schema")
            result = challenge(packet["nonce"], server.node)
        except (ValueError, RecursionError, OSError):
            self.respond(400, {"state": "REFUSED"})
            return
        self.respond(200, result)

    def do_GET(self):
        self.respond(405, {"state": "REFUSED"})


def server_context(cert, key):
    private_file(cert, 1024 * 1024)
    private_file(key, 1024 * 1024)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return context


def probe(ip, node, cert, pin, token_file, port=PORT):
    if not lan_ip(ip) or not NODE.fullmatch(node) or not HEX.fullmatch(pin):
        raise ValueError("explicit LAN trust required")
    private_file(cert, 1024 * 1024)
    token = token_from_file(token_file)
    # Reuse HomeNode trust-file validation and certificate chain/IP verification.
    context, loaded = load_trust(HomeNodeConfig(ip, port, pin, str(cert), str(token_file)))
    if not hmac.compare_digest(loaded, token):
        raise ValueError("trust file changed")
    nonce = secrets.token_hex(32)
    expected = challenge(nonce, node)
    connection = http.client.HTTPSConnection(ip, port, context=context, timeout=5)
    try:
        connection.connect()
        sock = connection.sock
        peer = sock.getpeercert(binary_form=True) if sock else None
        if not peer or not hmac.compare_digest(hashlib.sha256(peer).hexdigest(), pin):
            raise ValueError("certificate pin mismatch")
        # Authentication is sent only after verifying the live TLS certificate.
        connection.request("POST", "/v1/challenge",
                           body=canonical({"schema": SCHEMA, "nonce": nonce}),
                           headers={"Authorization": "Bearer " + token,
                                    "Content-Type": "application/json",
                                    "Connection": "close"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type") != "application/json":
            raise ValueError("peer refused")
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY or canonical(decode(raw)) != canonical(expected):
            raise ValueError("challenge mismatch")
        return dict(expected, state="PINNED_PEER_CHALLENGE_PASSED",
                    tls_pin_verified=True, remote_workload_authorized=False)
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--bind", required=True)
    serve.add_argument("--peer", required=True)
    serve.add_argument("--node", required=True)
    serve.add_argument("--cert", required=True, type=Path)
    serve.add_argument("--key", required=True, type=Path)
    serve.add_argument("--token-file", required=True, type=Path)
    serve.add_argument("--confirm-private-lan", action="store_true")
    client = sub.add_parser("probe")
    client.add_argument("--ip", required=True)
    client.add_argument("--node", required=True)
    client.add_argument("--cert", required=True, type=Path)
    client.add_argument("--pin", required=True)
    client.add_argument("--token-file", required=True, type=Path)
    client.add_argument("--confirm-private-lan", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_private_lan:
        parser.error("explicit private LAN confirmation required")
    try:
        if args.stage == "serve":
            if len({args.cert.resolve(), args.key.resolve(), args.token_file.resolve()}) != 3:
                raise ValueError("separate files required")
            with MeshServer(args.bind, args.peer, args.node, server_context(args.cert, args.key),
                            token_from_file(args.token_file)) as server:
                # One operator-started listener, bounded accept attempts; no daemon.
                print("MESH_LISTENING_CHALLENGE_ONLY", flush=True)
                for _ in range(3):
                    server.handle_request()
            return 0
        result = probe(args.ip, args.node, args.cert, args.pin, args.token_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, ssl.SSLError, http.client.HTTPException,
            HomeNodeTrustError, RecursionError):
        print("MESH_HELD: local trust, peer or challenge unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
