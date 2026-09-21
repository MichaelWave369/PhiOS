from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .validation import require_nonempty, require_sha256

CONFIG_VERSION = "phios.memory.config.v0.1"
_ALLOWED_KEYS = {
    "config_version",
    "enabled",
    "principal_id",
    "scopes",
    "classifications",
    "retention_policy_id",
    "semantic_enabled",
    "ollama_endpoint",
    "embedding_model",
    "embedding_dimensions",
    "embedding_model_digest",
    "evidence_horizon_enabled",
    "active_context_window_seconds",
    "reactivation_window_seconds",
    "fresh_evidence_window_seconds",
}


@dataclass(frozen=True, kw_only=True)
class MemoryRuntimeConfig:
    enabled: bool
    principal_id: str
    scopes: tuple[str, ...]
    classifications: tuple[str, ...]
    retention_policy_id: str
    semantic_enabled: bool = False
    ollama_endpoint: str = "http://127.0.0.1:11434"
    embedding_model: str = ""
    embedding_dimensions: int = 0
    embedding_model_digest: str | None = None
    evidence_horizon_enabled: bool = False
    active_context_window_seconds: float = 86_400.0
    reactivation_window_seconds: float = 2_592_000.0
    fresh_evidence_window_seconds: float = 21_600.0
    config_version: str = CONFIG_VERSION

    @classmethod
    def disabled_default(cls) -> "MemoryRuntimeConfig":
        return cls(
            enabled=False,
            principal_id="operator",
            scopes=("private",),
            classifications=("operator",),
            retention_policy_id="retain",
        )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "MemoryRuntimeConfig":
        unknown = set(raw) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(f"unknown memory config fields: {', '.join(sorted(unknown))}")
        version = raw.get("config_version", CONFIG_VERSION)
        if version != CONFIG_VERSION:
            raise ValueError("unsupported memory config version")
        enabled = raw.get("enabled", False)
        semantic_enabled = raw.get("semantic_enabled", False)
        horizon_enabled = raw.get("evidence_horizon_enabled", False)
        if (
            not isinstance(enabled, bool)
            or not isinstance(semantic_enabled, bool)
            or not isinstance(horizon_enabled, bool)
        ):
            raise ValueError(
                "enabled, semantic_enabled, and evidence_horizon_enabled "
                "must be booleans"
            )
        principal_id = require_nonempty(str(raw.get("principal_id", "operator")), "principal_id")
        scopes = _string_tuple(raw.get("scopes", ["private"]), "scopes")
        classifications = _string_tuple(
            raw.get("classifications", ["operator"]), "classifications"
        )
        retention = require_nonempty(
            str(raw.get("retention_policy_id", "retain")),
            "retention_policy_id",
        )
        endpoint = require_nonempty(
            str(raw.get("ollama_endpoint", "http://127.0.0.1:11434")),
            "ollama_endpoint",
        )
        model = str(raw.get("embedding_model", "")).strip()
        dimensions_raw = raw.get("embedding_dimensions", 0)
        if isinstance(dimensions_raw, bool) or not isinstance(dimensions_raw, int):
            raise ValueError("embedding_dimensions must be an integer")
        if semantic_enabled:
            if not model:
                raise ValueError("embedding_model is required when semantic_enabled=true")
            if dimensions_raw < 1 or dimensions_raw > 4096:
                raise ValueError("embedding_dimensions must be between 1 and 4096")
        elif dimensions_raw < 0:
            raise ValueError("embedding_dimensions must be >= 0")
        active_window = _positive_number(
            raw.get("active_context_window_seconds", 86_400.0),
            "active_context_window_seconds",
        )
        reactivation_window = _positive_number(
            raw.get("reactivation_window_seconds", 2_592_000.0),
            "reactivation_window_seconds",
        )
        fresh_window = _positive_number(
            raw.get("fresh_evidence_window_seconds", 21_600.0),
            "fresh_evidence_window_seconds",
        )
        if reactivation_window <= active_window:
            raise ValueError(
                "reactivation_window_seconds must exceed "
                "active_context_window_seconds"
            )
        if fresh_window > active_window:
            raise ValueError(
                "fresh_evidence_window_seconds cannot exceed "
                "active_context_window_seconds"
            )

        digest_raw = raw.get("embedding_model_digest")
        digest = None
        if digest_raw is not None:
            if not isinstance(digest_raw, str):
                raise ValueError("embedding_model_digest must be a string")
            digest = require_sha256(
                digest_raw.removeprefix("sha256:"),
                "embedding_model_digest",
            )
        return cls(
            enabled=enabled,
            principal_id=principal_id,
            scopes=scopes,
            classifications=classifications,
            retention_policy_id=retention,
            semantic_enabled=semantic_enabled,
            ollama_endpoint=endpoint,
            embedding_model=model,
            embedding_dimensions=dimensions_raw,
            embedding_model_digest=digest,
            evidence_horizon_enabled=horizon_enabled,
            active_context_window_seconds=active_window,
            reactivation_window_seconds=reactivation_window,
            fresh_evidence_window_seconds=fresh_window,
            config_version=CONFIG_VERSION,
        )

    @classmethod
    def load(cls, path: Path) -> "MemoryRuntimeConfig":
        try:
            raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"memory config does not exist: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"memory config is invalid JSON: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise ValueError("memory config must be a JSON object")
        return cls.from_mapping(raw)

    def to_dict(self) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "enabled": self.enabled,
            "principal_id": self.principal_id,
            "scopes": list(self.scopes),
            "classifications": list(self.classifications),
            "retention_policy_id": self.retention_policy_id,
            "semantic_enabled": self.semantic_enabled,
            "ollama_endpoint": self.ollama_endpoint,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_model_digest": self.embedding_model_digest,
            "evidence_horizon_enabled": self.evidence_horizon_enabled,
            "active_context_window_seconds": self.active_context_window_seconds,
            "reactivation_window_seconds": self.reactivation_window_seconds,
            "fresh_evidence_window_seconds": self.fresh_evidence_window_seconds,
        }


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty JSON array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} entries must be strings")
        normalized = require_nonempty(item, field)
        if normalized not in items:
            items.append(normalized)
    return tuple(items)


def write_disabled_template(path: Path, *, overwrite: bool = False) -> None:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    payload = MemoryRuntimeConfig.disabled_default().to_dict()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if number <= 0.0 or number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite and > 0")
    return number
