import math
import time
from typing import Any

import pytest

from phios.memory.embeddings import OllamaEmbeddingProvider


class FakeTransport:
    def __init__(self, *, vector: list[object] | None = None, include_model: bool = True) -> None:
        self.vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self.include_model = include_model
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, object] | None,
        timeout: float,
    ) -> dict[str, Any]:
        assert timeout > 0
        self.calls.append((method, url, payload))
        if url.endswith("/api/version"):
            return {"version": "0.34.2"}
        if url.endswith("/api/tags"):
            models = []
            if self.include_model:
                models.append(
                    {
                        "name": "embeddinggemma:latest",
                        "model": "embeddinggemma:latest",
                        "digest": "a" * 64,
                    }
                )
            return {"models": models}
        if url.endswith("/api/embed"):
            return {"embeddings": [self.vector]}
        raise AssertionError(url)


def test_ollama_provider_binds_local_model_identity_and_embedding() -> None:
    transport = FakeTransport()
    provider = OllamaEmbeddingProvider(
        endpoint="http://127.0.0.1:11434",
        model="embeddinggemma",
        dimensions=3,
        expected_digest="a" * 64,
        transport=transport,
    )
    vector = provider.embed("remember this", deadline=time.monotonic() + 5)
    identity = provider.identity()
    assert vector == (0.1, 0.2, 0.3)
    assert identity.provider == "ollama"
    assert identity.provider_version == "0.34.2"
    assert identity.model == "embeddinggemma:latest"
    assert identity.model_digest == "a" * 64
    assert identity.dimensions == 3
    embed_call = next(call for call in transport.calls if call[1].endswith("/api/embed"))
    assert embed_call[2] == {
        "model": "embeddinggemma:latest",
        "input": "remember this",
        "truncate": False,
    }


def test_remote_embedding_endpoint_is_rejected() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaEmbeddingProvider(
            endpoint="https://example.com",
            model="embeddinggemma",
            dimensions=3,
            transport=FakeTransport(),
        )


def test_missing_local_model_fails_without_embedding_call() -> None:
    transport = FakeTransport(include_model=False)
    provider = OllamaEmbeddingProvider(
        endpoint="http://localhost:11434",
        model="embeddinggemma",
        dimensions=3,
        transport=transport,
    )
    with pytest.raises(RuntimeError, match="not installed locally"):
        provider.embed("x", deadline=time.monotonic() + 5)
    assert not any(url.endswith("/api/embed") for _, url, _ in transport.calls)


@pytest.mark.parametrize("vector", [[0.1, 0.2], [0.1, True, 0.3], [0.1, math.nan, 0.3]])
def test_invalid_embedding_payload_is_rejected(vector: list[object]) -> None:
    provider = OllamaEmbeddingProvider(
        endpoint="http://localhost:11434",
        model="embeddinggemma",
        dimensions=3,
        transport=FakeTransport(vector=vector),
    )
    with pytest.raises(RuntimeError):
        provider.embed("x", deadline=time.monotonic() + 5)


def test_expired_deadline_fails_before_any_network_call() -> None:
    transport = FakeTransport()
    provider = OllamaEmbeddingProvider(
        endpoint="http://localhost:11434",
        model="embeddinggemma",
        dimensions=3,
        transport=transport,
    )
    with pytest.raises(TimeoutError):
        provider.embed("x", deadline=time.monotonic() - 1)
    assert transport.calls == []
