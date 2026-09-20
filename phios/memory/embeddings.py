from __future__ import annotations

import ipaddress
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from .models import EmbeddingIdentity
from .validation import require_nonempty, require_sha256, validate_text

MAX_EMBED_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_VECTOR_DIMENSIONS = 4096


class EmbeddingProvider(Protocol):
    def identity(self) -> EmbeddingIdentity: ...

    def embed(self, text: str, *, deadline: float) -> tuple[float, ...]: ...


class JsonTransport(Protocol):
    def request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None,
        timeout: float,
    ) -> dict[str, Any]: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


class UrllibJsonTransport:
    """Small no-proxy/no-redirect transport for a loopback Ollama endpoint."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
        )

    def request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None,
        timeout: float,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method=method,
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_EMBED_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise RuntimeError("local embedding endpoint unavailable") from exc
        if len(raw) > MAX_EMBED_RESPONSE_BYTES:
            raise RuntimeError("embedding response exceeds configured bound")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("embedding endpoint returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("embedding endpoint returned a non-object response")
        return decoded


def _canonical_model_name(model: str) -> str:
    normalized = require_nonempty(model, "model")
    tail = normalized.rsplit("/", 1)[-1]
    return normalized if ":" in tail else f"{normalized}:latest"


def _validate_loopback_endpoint(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(require_nonempty(endpoint, "endpoint"))
    if parsed.scheme != "http":
        raise ValueError("Ollama embedding endpoint must use http on loopback")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ollama embedding endpoint must not contain credentials/query/fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("Ollama embedding endpoint must be a server root")
    host = parsed.hostname
    if not host:
        raise ValueError("Ollama embedding endpoint requires a host")
    if host.lower() != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("Ollama embedding endpoint must be loopback")
        except ValueError as exc:
            if "must be loopback" in str(exc):
                raise
            raise ValueError("Ollama embedding endpoint must be loopback") from exc
    return endpoint.rstrip("/")


class OllamaEmbeddingProvider:
    """Explicit local embedding adapter. It never pulls models or falls back to cloud."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        dimensions: int,
        expected_digest: str | None = None,
        preprocessing_version: str = "text-v1",
        timeout: float = 10.0,
        transport: JsonTransport | None = None,
    ) -> None:
        if isinstance(dimensions, bool) or not isinstance(dimensions, int):
            raise ValueError("dimensions must be an integer")
        if dimensions < 1 or dimensions > MAX_VECTOR_DIMENSIONS:
            raise ValueError(f"dimensions must be between 1 and {MAX_VECTOR_DIMENSIONS}")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.endpoint = _validate_loopback_endpoint(endpoint)
        self.model = _canonical_model_name(model)
        self.dimensions = dimensions
        self.expected_digest = (
            require_sha256(expected_digest.removeprefix("sha256:"), "expected_digest")
            if expected_digest
            else None
        )
        self.preprocessing_version = require_nonempty(
            preprocessing_version, "preprocessing_version"
        )
        self.timeout = float(timeout)
        self.transport = transport or UrllibJsonTransport()
        self._identity: EmbeddingIdentity | None = None

    def identity(self) -> EmbeddingIdentity:
        if self._identity is None:
            self._identity = self._resolve_identity()
        return self._identity

    def _resolve_identity(self, *, timeout: float | None = None) -> EmbeddingIdentity:
        request_timeout = self.timeout if timeout is None else min(self.timeout, timeout)
        if request_timeout <= 0:
            raise TimeoutError("embedding deadline expired")
        version_payload = self.transport.request_json(
            "GET",
            f"{self.endpoint}/api/version",
            payload=None,
            timeout=request_timeout,
        )
        provider_version = require_nonempty(str(version_payload.get("version", "")), "version")
        tags = self.transport.request_json(
            "GET",
            f"{self.endpoint}/api/tags",
            payload=None,
            timeout=request_timeout,
        )
        models = tags.get("models")
        if not isinstance(models, list):
            raise RuntimeError("Ollama tags response has no model list")
        match: dict[str, Any] | None = None
        for item in models:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("model") or item.get("name") or "").strip()
            if not candidate:
                continue
            if _canonical_model_name(candidate) == self.model:
                match = item
                break
        if match is None:
            raise RuntimeError("configured embedding model is not installed locally")
        raw_digest = str(match.get("digest", "")).removeprefix("sha256:")
        digest = require_sha256(raw_digest, "model_digest")
        if self.expected_digest is not None and digest != self.expected_digest:
            raise RuntimeError("local embedding model digest does not match configured digest")
        return EmbeddingIdentity(
            provider="ollama",
            provider_version=provider_version,
            model=self.model,
            model_digest=digest,
            dimensions=self.dimensions,
            preprocessing_version=self.preprocessing_version,
            metric="l2",
        )

    def embed(self, text: str, *, deadline: float) -> tuple[float, ...]:
        text = validate_text(text)
        remaining = min(self.timeout, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("embedding deadline expired")
        # Refresh immediately before inference so the receipt binds the local artifact used.
        self._identity = self._resolve_identity(timeout=remaining)
        remaining = min(self.timeout, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("embedding deadline expired")
        payload = self.transport.request_json(
            "POST",
            f"{self.endpoint}/api/embed",
            payload={"model": self.model, "input": text, "truncate": False},
            timeout=remaining,
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            raise RuntimeError("embedding response must contain exactly one vector")
        raw_vector = embeddings[0]
        if not isinstance(raw_vector, list) or len(raw_vector) != self.dimensions:
            raise RuntimeError("embedding vector dimension mismatch")
        vector: list[float] = []
        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RuntimeError("embedding vector contains a non-numeric value")
            number = float(value)
            if not math.isfinite(number):
                raise RuntimeError("embedding vector contains a non-finite value")
            vector.append(number)
        return tuple(vector)
