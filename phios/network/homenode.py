"""PhiOS HomeNode R1-H6: bounded native client for GitPorch R1-H4 capabilities.

Capability observation is not authorization, Git integrity, or offline readiness.
Only explicit LOCAL mode may contact the configured private-IP HomeNode.
No daemon, browser origin, credential persistence, or auto-fallback to public internet.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SCHEMA = "phios.homenode-observation.v0.1"
GATEWAY_SCHEMA = "gitporch.homenode.capabilities.v1"
EXPECTED_TRANSPORT = "HTTPS_WITH_OPERATOR_TRUSTED_CERTIFICATE"
EXPECTED_MODE = "EXPERIMENTAL_AUTHENTICATED_READ_ONLY"
MAX_BODY = 16 * 1024
TIMEOUT_SECONDS = 5.0
_ALLOWED_CAPABILITIES = ("localGitStorage", "localSnapshots", "publicGitHubImport")
_FORBIDDEN_CAPABILITIES = (
    "remoteRepositoryRead",
    "remoteGitPush",
    "remoteBuilds",
    "browserAccess",
    "automaticSync",
)


class HomeNodeTrustError(ValueError):
    """Configuration, trust, or protocol contract failure without secret detail."""


def _private_ip(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        return False
    octets = address.packed
    return (
        octets[0] == 127
        or octets[0] == 10
        or (octets[0] == 172 and 16 <= octets[1] <= 31)
        or (octets[0] == 192 and octets[1] == 168)
    )


def _read_private_file(value: str, *, limit: int) -> bytes:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    try:
        if not 0 < path.stat().st_size <= limit:
            raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
        return path.read_bytes()
    except OSError as exc:
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED") from exc


@dataclass(frozen=True)
class HomeNodeConfig:
    ip: str
    port: int
    pin_sha256: str
    cert_file: str
    token_file: str


def config_from_env(env: Mapping[str, str] | None = None) -> HomeNodeConfig:
    values = os.environ if env is None else env
    ip = values.get("PHIOS_HOMENODE_IP", "")
    if not _private_ip(ip):
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    port_text = values.get("PHIOS_HOMENODE_PORT", "3743")
    if not re.fullmatch(r"[0-9]{1,5}", port_text):
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    port = int(port_text)
    if not 1024 <= port <= 65535:
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    pin = values.get("PHIOS_HOMENODE_CERT_SHA256", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", pin):
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    cert_file = values.get("PHIOS_HOMENODE_CERT_FILE", "")
    token_file = values.get("PHIOS_HOMENODE_TOKEN_FILE", "")
    if not cert_file or not token_file:
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    if Path(cert_file).resolve() == Path(token_file).resolve():
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    return HomeNodeConfig(ip, port, pin, cert_file, token_file)


def load_trust(config: HomeNodeConfig) -> tuple[ssl.SSLContext, str]:
    certificate_pem = _read_private_file(config.cert_file, limit=1024 * 1024)
    raw_token = _read_private_file(config.token_file, limit=1024)
    try:
        token = raw_token.decode("ascii").rstrip("\r\n")
        certificate_text = certificate_pem.decode("ascii")
        cert_der = ssl.PEM_cert_to_DER_cert(certificate_text)
    except (UnicodeError, ValueError) as exc:
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED") from exc
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,256}", token):
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED")
    actual_pin = hashlib.sha256(cert_der).hexdigest()
    if not hmac.compare_digest(actual_pin, config.pin_sha256):
        raise HomeNodeTrustError("LOCAL_UNTRUSTED")
    try:
        context = ssl.create_default_context(cadata=certificate_text)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except (ssl.SSLError, ValueError) as exc:
        raise HomeNodeTrustError("LOCAL_CONFIGURATION_REQUIRED") from exc
    return context, token


def _validate_payload(payload: object) -> dict[str, bool]:
    if not isinstance(payload, dict):
        raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
    if (
        payload.get("schema") != GATEWAY_SCHEMA
        or payload.get("mode") != EXPECTED_MODE
        or payload.get("transport") != EXPECTED_TRANSPORT
    ):
        raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
    caps = payload.get("capabilities")
    if not isinstance(caps, dict):
        raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
    for key in _ALLOWED_CAPABILITIES + _FORBIDDEN_CAPABILITIES:
        if type(caps.get(key)) is not bool:
            raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
    if any(caps[key] is not False for key in _FORBIDDEN_CAPABILITIES):
        raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
    return {key: caps[key] for key in _ALLOWED_CAPABILITIES}


def probe_gateway(config: HomeNodeConfig) -> dict[str, bool]:
    context, token = load_trust(config)
    connection = http.client.HTTPSConnection(
        config.ip, config.port, context=context, timeout=TIMEOUT_SECONDS
    )
    try:
        # Pin before sending the bearer token. TLS must also validate the IP SAN.
        connection.connect()
        if connection.sock is None:
            raise HomeNodeTrustError("LOCAL_UNTRUSTED")
        peer = connection.sock.getpeercert(binary_form=True)
        if not peer or not hmac.compare_digest(
            hashlib.sha256(peer).hexdigest(), config.pin_sha256
        ):
            raise HomeNodeTrustError("LOCAL_UNTRUSTED")
        connection.request(
            "GET",
            "/v1/capabilities",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise HomeNodeTrustError("LOCAL_REJECTED")
        if not response.getheader("Content-Type", "").lower().startswith("application/json"):
            raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise HomeNodeTrustError("LOCAL_BAD_RESPONSE")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise HomeNodeTrustError("LOCAL_BAD_RESPONSE") from exc
        return _validate_payload(payload)
    finally:
        connection.close()


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, HomeNodeTrustError):
        return str(exc)
    if isinstance(exc, (ssl.SSLError, ssl.CertificateError)):
        return "LOCAL_UNTRUSTED"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "LOCAL_TIMEOUT"
    return "LOCAL_UNAVAILABLE"


def select_mode(
    mode: str, *, env: Mapping[str, str] | None = None
) -> dict[str, object]:
    requested = mode.upper()
    if requested not in {"PUBLIC", "LOCAL", "OFFLINE"}:
        raise ValueError("Expected PUBLIC, LOCAL, or OFFLINE")
    base: dict[str, object] = {
        "schema": SCHEMA,
        "requestedMode": requested,
        "gatewayVerified": False,
        "offlineServicesVerified": False,
        "actionAuthority": False,
        "note": "Mode selection cannot certify Git history, builds, backups, or models.",
    }
    if requested == "OFFLINE":
        return {**base, "effectiveMode": "OFFLINE", "status": "OFFLINE_SELECTED_NOT_VERIFIED"}
    if requested == "PUBLIC":
        return {**base, "effectiveMode": "PUBLIC", "status": "PUBLIC_SELECTED_NOT_PROBED"}
    try:
        capabilities = probe_gateway(config_from_env(env))
        return {
            **base,
            "effectiveMode": "LOCAL",
            "status": "LOCAL_GATEWAY_VERIFIED_ONLY",
            "gatewayVerified": True,
            "capabilities": capabilities,
        }
    except Exception as exc:
        # Do not echo raw SSL/socket/OSError strings: they can contain local paths.
        return {
            **base,
            "effectiveMode": "OFFLINE",
            "status": "LOCAL_FAILED_OFFLINE_MODE_SELECTED",
            "failure": _failure_category(exc),
            "capabilities": None,
        }
