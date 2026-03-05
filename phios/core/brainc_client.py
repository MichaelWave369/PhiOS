"""Local AI connectivity helpers with TTL-cached availability probe."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from typing import TypedDict

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
_CACHE_TTL_SECONDS = 30.0


class OllamaCacheEntry(TypedDict):
    checked_at: float
    available: bool


_CACHE: dict[str, OllamaCacheEntry] = {}


def get_ollama_url() -> str:
    """Return configured local Ollama URL from environment."""
    return os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)


def clear_ollama_cache() -> None:
    """Clear cached availability status (for tests/manual refresh)."""
    _CACHE.clear()


def _probe_ollama(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, ValueError, OSError):
        return False


def ollama_available(timeout: float = 0.2) -> bool:
    """Return whether local Ollama endpoint responds, using a short TTL cache."""
    url = get_ollama_url()
    now = time.monotonic()
    cached = _CACHE.get(url)
    if cached and now - cached["checked_at"] < _CACHE_TTL_SECONDS:
        return cached["available"]

    available = _probe_ollama(url, timeout)
    _CACHE[url] = {"checked_at": now, "available": available}
    return available
