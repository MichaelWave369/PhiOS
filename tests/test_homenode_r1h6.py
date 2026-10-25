"""PhiOS R1-H6 client contract against GitPorch R1-H4's fixed capabilities schema."""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from phios.network.homenode import (
    GATEWAY_SCHEMA,
    HomeNodeTrustError,
    config_from_env,
    load_trust,
    select_mode,
)
from phios.network.homenode_cli import main as cli_main


TOKEN = "0123456789abcdef" * 4
CAPABILITIES = {
    "schema": GATEWAY_SCHEMA,
    "mode": "EXPERIMENTAL_AUTHENTICATED_READ_ONLY",
    "transport": "HTTPS_WITH_OPERATOR_TRUSTED_CERTIFICATE",
    "capabilities": {
        "localGitStorage": True,
        "localSnapshots": True,
        "publicGitHubImport": True,
        "remoteRepositoryRead": False,
        "remoteGitPush": False,
        "remoteBuilds": False,
        "browserAccess": False,
        "automaticSync": False,
    },
}


def _env(path: Path, pin: str, port: int) -> dict[str, str]:
    return {
        "PHIOS_HOMENODE_IP": "127.0.0.1",
        "PHIOS_HOMENODE_PORT": str(port),
        "PHIOS_HOMENODE_CERT_FILE": str(path / "cert.pem"),
        "PHIOS_HOMENODE_TOKEN_FILE": str(path / "token.txt"),
        "PHIOS_HOMENODE_CERT_SHA256": pin,
    }


def test_public_offline_modes_do_not_read_credentials_or_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    import phios.network.homenode as bridge

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("PUBLIC/OFFLINE must not probe the network")

    monkeypatch.setattr(bridge, "probe_gateway", no_network)
    for mode, expected in [
        ("public", "PUBLIC_SELECTED_NOT_PROBED"),
        ("offline", "OFFLINE_SELECTED_NOT_VERIFIED"),
    ]:
        result = select_mode(mode, env={})
        assert result["status"] == expected
        assert result["gatewayVerified"] is False
        assert result["actionAuthority"] is False
        assert result["offlineServicesVerified"] is False
    with pytest.raises(ValueError, match="Expected PUBLIC"):
        select_mode("auto")


@pytest.mark.parametrize("ip", [
    "0.0.0.0", "8.8.8.8", "169.254.3.9", "172.32.1.1",
    "100.64.0.1", "::1", "localhost", "192.168.2.999",
])
def test_public_or_untrusted_ip_fails_closed(ip: str) -> None:
    result = select_mode("local", env={**_env(Path("/tmp"), "a" * 64, 3743),
                                       "PHIOS_HOMENODE_IP": ip})
    assert result["status"] == "LOCAL_FAILED_OFFLINE_MODE_SELECTED"
    assert result["failure"] == "LOCAL_CONFIGURATION_REQUIRED"
    assert result["effectiveMode"] == "OFFLINE"
    assert result["offlineServicesVerified"] is False


@pytest.mark.parametrize("port", ["-1", "80", "0", "x", "65536"])
def test_invalid_port_rejected(port: str) -> None:
    with pytest.raises(HomeNodeTrustError, match="LOCAL_CONFIGURATION_REQUIRED"):
        config_from_env({**_env(Path("/tmp"), "a" * 64, 3743),
                         "PHIOS_HOMENODE_PORT": port})


def test_cli_explicit_offline_and_public_no_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for mode in ("offline", "public"):
        assert cli_main(["status", "--mode", mode]) == 0
        assert json.loads(capsys.readouterr().out)["requestedMode"] == mode.upper()


def test_missing_credentials_never_leak_private_paths() -> None:
    sensitive = "/not/a/real/path/my-secret-token"
    result = select_mode("local", env={
        **_env(Path("/tmp"), "a" * 64, 3743),
        "PHIOS_HOMENODE_TOKEN_FILE": sensitive,
    })
    assert result["failure"] == "LOCAL_CONFIGURATION_REQUIRED"
    assert sensitive not in json.dumps(result)
    assert result["effectiveMode"] == "OFFLINE"


@pytest.fixture()
def tls_server(tmp_path: Path) -> Iterator[tuple[dict[str, str], dict[str, object]]]:
    if shutil.which("openssl") is None:
        pytest.skip("OpenSSL CLI unavailable")
    result = subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(tmp_path / "key.pem"),
            "-out", str(tmp_path / "cert.pem"),
            "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        pytest.skip("OpenSSL installed but lacks IP-SAN self-signed cert generation")
    (tmp_path / "token.txt").write_text(TOKEN, encoding="ascii")
    cert_pem = (tmp_path / "cert.pem").read_text(encoding="ascii")
    der = ssl.PEM_cert_to_DER_cert(cert_pem)
    pin = hashlib.sha256(der).hexdigest()
    state: dict[str, object] = {"payload": CAPABILITIES, "token": TOKEN}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if (self.path != "/v1/capabilities" or
                    self.headers.get("Authorization") != "Bearer " + str(state["token"])):
                self.send_response(401)
                self.end_headers()
                return
            body = json.dumps(state["payload"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(tmp_path / "cert.pem"), str(tmp_path / "key.pem"))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = _env(tmp_path, pin, server.server_port)
    try:
        yield env, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_tls_pin_token_and_schema_are_required(
    tls_server: tuple[dict[str, str], dict[str, object]]
) -> None:
    env, state = tls_server
    good = select_mode("local", env=env)
    assert good["effectiveMode"] == "LOCAL"
    assert good["gatewayVerified"] is True
    assert good["status"] == "LOCAL_GATEWAY_VERIFIED_ONLY"
    assert good["capabilities"]["localSnapshots"] is True
    assert TOKEN not in json.dumps(good)

    wrong_pin = select_mode("local", env={
        **env, "PHIOS_HOMENODE_CERT_SHA256": "f" * 64
    })
    assert wrong_pin["failure"] == "LOCAL_UNTRUSTED"
    assert wrong_pin["effectiveMode"] == "OFFLINE"

    state["token"] = "something-else-" + "c" * 64
    unauthorized = select_mode("local", env=env)
    assert unauthorized["failure"] == "LOCAL_REJECTED"

    state["token"] = TOKEN
    state["payload"] = {**CAPABILITIES, "schema": "untrusted"}
    malformed = select_mode("local", env=env)
    assert malformed["failure"] == "LOCAL_BAD_RESPONSE"

    state["payload"] = {**CAPABILITIES, "capabilities": {
        **CAPABILITIES["capabilities"], "remoteGitPush": True
    }}
    elevated = select_mode("local", env=env)
    assert elevated["failure"] == "LOCAL_BAD_RESPONSE"


def test_symlink_token_refused_when_supported(
    tls_server: tuple[dict[str, str], dict[str, object]], tmp_path: Path
) -> None:
    env, _ = tls_server
    alias = tmp_path / "link-token"
    try:
        alias.symlink_to(Path(env["PHIOS_HOMENODE_TOKEN_FILE"]))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    config = config_from_env({**env, "PHIOS_HOMENODE_TOKEN_FILE": str(alias)})
    with pytest.raises(HomeNodeTrustError, match="LOCAL_CONFIGURATION_REQUIRED"):
        load_trust(config)


def test_missing_local_credentials_do_not_claim_offline_health(tmp_path: Path) -> None:
    # Missing credentials fail before network, regardless of address availability.
    result = select_mode("local", env=_env(tmp_path, "0" * 64, 3743))
    assert result["effectiveMode"] == "OFFLINE"
    assert result["gatewayVerified"] is False
    assert result["offlineServicesVerified"] is False
