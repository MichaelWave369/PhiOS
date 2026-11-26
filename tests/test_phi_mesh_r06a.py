"""R06-A tests: real local TLS socket when OpenSSL CLI is available."""
import hashlib
import http.client
import shutil
import ssl
import subprocess
import threading
from unittest.mock import patch

import pytest

from scripts import phi_mesh_r06a as mesh


@pytest.mark.parametrize("ip", ["0.0.0.0", "8.8.8.8", "169.254.1.1", "::1", "localhost", "127.0.0.2"])
def test_reject_non_lan(ip):
    assert not mesh.lan_ip(ip)


def test_fixed_challenge():
    nonce = "a" * 64
    value = bytes.fromhex(nonce)
    for _ in range(369):
        value = hashlib.sha256(value).digest()
    result = mesh.challenge(nonce, "node02")
    assert result["result_sha256"] == value.hex()
    assert not result["execution_authority"] and not result["offline_verified"]
    with pytest.raises(ValueError):
        mesh.challenge("bad", "node02")
    with pytest.raises(ValueError):
        mesh.decode(b'{"nonce":"a","nonce":"b"}')


@pytest.fixture
def trust(tmp_path):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("OpenSSL CLI needed for ephemeral local TLS fixture")
    cert, key, token = [tmp_path / n for n in ("cert.pem", "key.pem", "token.txt")]
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=mesh-test", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    token.write_text("b" * 64)
    pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    return cert, key, token, pin


def with_server(trust, operation):
    cert, key, token, pin = trust
    with mesh.MeshServer("127.0.0.1", "127.0.0.1", "node02",
                         mesh.server_context(cert, key), mesh.token_from_file(token), port=0) as server:
        server.timeout = 6
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            return operation(server.server_port)
        finally:
            thread.join(8)
            assert not thread.is_alive()


def test_real_tls_challenge(trust):
    cert, _, token, pin = trust
    receipt = with_server(trust, lambda port: mesh.probe("127.0.0.1", "node02",
                                                        cert, pin, token, port))
    assert receipt["state"] == "PINNED_PEER_CHALLENGE_PASSED"
    assert receipt["tls_pin_verified"] and not receipt["remote_workload_authorized"]


def test_wrong_pin_refuses_before_network(trust):
    cert, _, token, _ = trust
    with patch.object(mesh.http.client, "HTTPSConnection") as conn:
        with pytest.raises(ValueError):
            mesh.probe("127.0.0.1", "node02", cert, "0"*64, token)
        conn.assert_not_called()


@pytest.mark.parametrize("change", ["wrong_token", "origin", "extra_field"])
def test_real_tls_refusal(trust, change):
    cert, _, token, _ = trust
    context = ssl.create_default_context(cafile=str(cert))
    def run(port):
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=5)
        headers = {"Authorization": "Bearer " + ("c"*64 if change == "wrong_token" else token.read_text()),
                   "Content-Type": "application/json"}
        packet = {"schema": mesh.SCHEMA, "nonce": "a"*64}
        if change == "origin":
            headers["Origin"] = "https://example.invalid"
        if change == "extra_field":
            packet["command"] = "not authorized"
        try:
            conn.request("POST", "/v1/challenge", body=mesh.canonical(packet), headers=headers)
            response = conn.getresponse()
            assert response.status == (400 if change == "extra_field" else 403)
            assert mesh.decode(response.read()) == {"state": "REFUSED"}
        finally:
            conn.close()
    with_server(trust, run)


def test_no_implicit_network():
    with patch.object(mesh, "probe") as call, pytest.raises(SystemExit):
        mesh.main(["probe", "--ip", "192.168.1.2", "--node", "node02",
                   "--cert", "cert.pem", "--pin", "a"*64, "--token-file", "token.txt"])
    call.assert_not_called()
