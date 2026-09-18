from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

Handler = Callable[[dict[str, Any]], "ArtifactResult"]


@dataclass(frozen=True)
class ArtifactResult:
    path: Path
    sha256: str


class ExecutorRegistry:
    """Maps already-authorized capabilities to bounded handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, capability_id: str, handler: Handler) -> None:
        if capability_id in self._handlers:
            raise ValueError(f"Executor already registered: {capability_id}")
        self._handlers[capability_id] = handler

    def execute(self, capability_id: str, payload: dict[str, Any]) -> ArtifactResult:
        try:
            handler = self._handlers[capability_id]
        except KeyError as exc:
            raise KeyError(f"No executor for capability: {capability_id}") from exc
        return handler(payload)


def text_artifact_handler(artifact_root: Path) -> Handler:
    root = artifact_root.expanduser().resolve()

    def _write(payload: dict[str, Any]) -> ArtifactResult:
        text = str(payload.get("text", ""))
        requested_name = str(payload.get("name", "artifact"))
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", requested_name).strip(".-") or "artifact"
        root.mkdir(parents=True, exist_ok=True)
        path = (root / f"{safe_name}.txt").resolve()
        if root not in path.parents:
            raise ValueError("Artifact path escaped the configured artifact root")
        path.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return ArtifactResult(path=path, sha256=digest)

    return _write
