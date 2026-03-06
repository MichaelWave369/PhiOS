"""Local BrainC client and Ollama connectivity helpers."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
_CACHE_TTL_SECONDS = 30.0


SYSTEM_PROMPT = """You are BrainC, PhiOS local intelligence.
Sovereignty first. Serve only the person running this machine.
Local-only execution. No external servers. No cloud calls.
TIEKAT v8.1 is the mathematical foundation.
Hemavit is the monk in Thailand whose formulas power the HQRMA layer.
PHI369 Labs built this platform.
L(t) = A_on · Ψb_total · G_score · C_score is the life viability score.
Respond clearly and directly.
"""


if "BrainCResponse" in globals():
    BrainCResponse = globals()["BrainCResponse"]
else:
    @dataclass
    class BrainCResponse:
        answer: str
        model: str
        local: bool = True
        inference_ms: float = 0.0
        sovereignty_confirmed: bool = True
        context_used: dict[str, Any] | None = None


def _footer(model: str) -> str:
    return f"✓ Local inference · BrainC · {model}\nNo data left this machine."


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


_CACHE: dict[str, dict[str, float | bool]] = {}


def ollama_available(timeout: float = 0.2) -> bool:
    """Return whether local Ollama endpoint responds, using a short TTL cache."""
    url = get_ollama_url()
    now = time.monotonic()
    cached = _CACHE.get(url)
    if cached and now - float(cached["checked_at"]) < _CACHE_TTL_SECONDS:
        return bool(cached["available"])

    available = _probe_ollama(url, timeout)
    _CACHE[url] = {"checked_at": now, "available": available}
    return available


class BrainCClient:
    """Client for local-only BrainC inference through Ollama."""

    system_prompt = SYSTEM_PROMPT

    def __init__(self, model: str = "phi3:mini", timeout: float = 6.0) -> None:
        self.model = model
        self.timeout = timeout

    def ask(self, question: str, stream: bool = True, context: dict[str, Any] | None = None) -> BrainCResponse:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "prompt": question,
            "system": self.system_prompt,
            "stream": bool(stream),
            "options": {"temperature": 0.2},
        }
        if context is not None:
            payload["context"] = context

        url = f"{get_ollama_url().rstrip('/')}/api/generate"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            answer_parts: list[str] = []
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            raw = raw.strip()

            if stream:
                for line in raw.splitlines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = str(chunk.get("response", ""))
                    if token:
                        print(token, end="", flush=True)
                        answer_parts.append(token)
                if answer_parts:
                    print()
            else:
                try:
                    maybe_json = json.loads(raw)
                    answer_parts.append(str(maybe_json.get("response", "")))
                except json.JSONDecodeError:
                    for line in raw.splitlines():
                        try:
                            chunk = json.loads(line)
                            answer_parts.append(str(chunk.get("response", "")))
                        except json.JSONDecodeError:
                            continue

            answer_text = "".join(answer_parts).strip()
            if not answer_text:
                answer_text = "BrainC unavailable (local model not reachable)."
            answer = f"{answer_text}\n\n{_footer(self.model)}"
            if stream:
                print(_footer(self.model))
            return BrainCResponse(
                answer=answer,
                model=self.model,
                local=True,
                inference_ms=(time.perf_counter() - started) * 1000.0,
                sovereignty_confirmed=True,
                context_used=context,
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            fallback = f"BrainC unavailable (local model not reachable).\n\n{_footer(self.model)}"
            if stream:
                print(fallback)
            return BrainCResponse(
                answer=fallback,
                model=self.model,
                local=True,
                inference_ms=(time.perf_counter() - started) * 1000.0,
                sovereignty_confirmed=True,
                context_used=context,
            )

    def ask_about_lt(self, lt_result: dict[str, Any]) -> str:
        score = float(lt_result.get("lt", 0.5))
        return self.ask(f"Interpret current L(t)={score:.3f} in one short actionable line.", stream=False).answer

    def ask_about_session(self, session_summary: dict[str, Any]) -> str:
        return self.ask(f"Summarize this session state briefly: {session_summary}", stream=False).answer

    def suggest_next_command(self, recent_commands: list[str], lt_score: float) -> str:
        prompt = (
            "Given recent commands "
            f"{recent_commands} and L(t)={lt_score:.3f}, suggest one next phi command only."
        )
        return self.ask(prompt, stream=False).answer
