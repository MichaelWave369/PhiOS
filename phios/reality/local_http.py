from __future__ import annotations

import hashlib
from http.client import HTTPConnection, HTTPException, HTTPResponse
import ipaddress
import platform
import socket
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit


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


class StdlibLoopbackHttpStateProvider:
    """Bounded GET-only loopback HTTP observation using Python's standard library."""

    name = "stdlib-loopback-http"
    _safe_response_headers = frozenset(
        {
            "cache-control",
            "content-encoding",
            "content-length",
            "content-type",
            "etag",
            "last-modified",
        }
    )

    @staticmethod
    def _resolve_loopback_addresses(host: str, port: int) -> tuple[str, ...]:
        try:
            records = socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise LocalHttpObservationError(
                "local_http_resolution_failed",
                "loopback host resolution failed",
            ) from exc

        addresses: list[str] = []
        for _family, _socktype, _proto, _canonname, sockaddr in records:
            raw_address = str(sockaddr[0])
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as exc:
                raise LocalHttpObservationError(
                    "local_http_resolution_failed",
                    "resolver returned a non-IP address",
                ) from exc
            if not address.is_loopback:
                raise LocalHttpObservationError(
                    "local_http_resolution_not_loopback",
                    "loopback hostname resolved to a non-loopback address",
                )
            addresses.append(str(address))

        unique_addresses = tuple(dict.fromkeys(addresses))
        if not unique_addresses:
            raise LocalHttpObservationError(
                "local_http_resolution_failed",
                "loopback host resolution returned no addresses",
            )
        return unique_addresses

    @classmethod
    def _safe_headers(cls, response: HTTPResponse) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in response.getheaders():
            normalized = name.lower()
            if normalized in cls._safe_response_headers:
                headers[normalized] = value
        return headers

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        validation_error = local_http_url_error(url)
        if validation_error is not None:
            raise LocalHttpObservationError(
                validation_error,
                "URL does not satisfy the bounded loopback HTTP contract",
            )
        if not 0.1 <= timeout_seconds <= 10.0:
            raise LocalHttpObservationError(
                "local_http_claim_invalid_timeout",
                "timeout is outside the bounded HTTP contract",
            )
        if not 1 <= max_body_bytes <= 1_048_576:
            raise LocalHttpObservationError(
                "local_http_claim_invalid_body_budget",
                "body budget is outside the bounded HTTP contract",
            )

        parsed = urlsplit(url)
        host = parsed.hostname
        assert host is not None
        port = parsed.port or 80
        addresses = self._resolve_loopback_addresses(host, port)
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        request_headers = {
            "Accept": "*/*",
            "Connection": "close",
            "Host": parsed.netloc,
            "User-Agent": "PhiOS-Spine/0.14",
        }

        started = time.monotonic()
        deadline = started + timeout_seconds
        last_code = "local_http_connection_failed"
        last_message = "all loopback connection attempts failed"

        for connect_host in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_code = "local_http_timeout"
                last_message = "loopback HTTP observation exceeded its timeout"
                break

            connection = HTTPConnection(connect_host, port=port, timeout=remaining)
            try:
                connection.request("GET", target, headers=request_headers)
                response = connection.getresponse()
                body_with_sentinel = response.read(max_body_bytes + 1)
                body_truncated = len(body_with_sentinel) > max_body_bytes
                body = body_with_sentinel[:max_body_bytes]
                elapsed_ms = (time.monotonic() - started) * 1000.0

                return LocalHttpObservation(
                    url=url,
                    method="GET",
                    status_code=response.status,
                    reason=str(response.reason or ""),
                    headers=self._safe_headers(response),
                    body_sha256=hashlib.sha256(body).hexdigest(),
                    body_bytes_observed=len(body),
                    body_truncated=body_truncated,
                    body_digest_scope="prefix" if body_truncated else "full",
                    redirect_followed=False,
                    timeout_seconds=timeout_seconds,
                    max_body_bytes=max_body_bytes,
                    elapsed_ms=elapsed_ms,
                    provider=self.name,
                    provider_version=platform.python_version(),
                    captured_at_utc=datetime.now(UTC).isoformat(),
                )
            except (TimeoutError, socket.timeout):
                last_code = "local_http_timeout"
                last_message = "loopback HTTP observation exceeded its timeout"
            except HTTPException:
                last_code = "local_http_protocol_error"
                last_message = "loopback endpoint returned an invalid HTTP response"
            except OSError:
                last_code = "local_http_connection_failed"
                last_message = "loopback HTTP connection failed"
            finally:
                connection.close()

        raise LocalHttpObservationError(last_code, last_message)
