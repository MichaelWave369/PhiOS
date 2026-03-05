"""Local AI connectivity helpers."""

from __future__ import annotations

import urllib.request


OLLAMA_URL = "http://localhost:11434"


def ollama_available(timeout: float = 0.2) -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=timeout):
            return True
    except Exception:
        return False
