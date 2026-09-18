from __future__ import annotations

import ipaddress
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit


class LocalHttpObservationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def local_http_url_error(url: str | None) -> str | None:
    if url is None or not url.strip():
        return "local_http_claim_requires_url"

    try:
        parsed = urlsplit(url)
    except ValueError:
        return "local_http_claim_invalid_url"

    if parsed.scheme.lower() != "http":
        return "local_http_claim_requires_http_scheme"
    if parsed.username is not None or parsed.password is not None:
        return "local_http_claim_disallows_userinfo"
    if parsed.fragment:
        return "local_http_claim_disallows_fragment"

    host = parsed.hostname
    if host is None:
        return "local_http_claim_requires_host"

    host_lower = host.lower()
    if host_lower != "localhost":
        try:
            address = ipaddress.ip_address(host_lower)
        except ValueError:
            return "local_http_claim_requires_loopback_host"
        if not address.is_loopback:
            return "local_http_claim_requires_loopback_host"

    try:
        port = parsed.port
    except ValueError:
        return "local_http_claim_invalid_port"

    if port is not None and not 1 <= port <= 65535:
        return "local_http_claim_invalid_port"

    return None


@dataclass(frozen=True, kw_only=True)
class LocalHttpObservation:
    url: str
    method: str
    status_code: int
    reason: str
    headers: dict[str, str]
    body_sha256: str
    body_bytes_observed: int
    body_truncated: bool
    body_digest_scope: str
    redirect_followed: bool
    timeout_seconds: float
    max_body_bytes: int
    elapsed_ms: float
    provider: str
    provider_version: str | None
    captured_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalHttpStateProvider(Protocol):
    name: str

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        ...


class UnavailableLocalHttpStateProvider:
    """Fail-closed placeholder until a transport adapter is explicitly installed."""

    name = "local-http-unavailable"

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        raise LocalHttpObservationError(
            "local_http_provider_unavailable",
            "no live local HTTP transport adapter is installed",
        )
