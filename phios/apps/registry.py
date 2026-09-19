from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .manifest import AppManifest

APP_REGISTRY_SCHEMA_VERSION = "phios.app_registry.v0.1"


class AppRegistry:
    """Strict app registry. Registration never implies install or execution authority."""

    def __init__(self) -> None:
        self._apps: dict[str, AppManifest] = {}

    def register(self, manifest: AppManifest) -> None:
        if manifest.app_id in self._apps:
            raise ValueError(f"App already registered: {manifest.app_id}")
        self._apps[manifest.app_id] = manifest

    def get(self, app_id: str) -> AppManifest:
        try:
            return self._apps[app_id]
        except KeyError as exc:
            raise KeyError(f"Unknown app: {app_id}") from exc

    def list(self) -> list[AppManifest]:
        return sorted(self._apps.values(), key=lambda item: item.app_id)

    def manifest_digest(self, app_id: str) -> str:
        return self.get(app_id).sha256()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": APP_REGISTRY_SCHEMA_VERSION,
            "apps": [
                {
                    "manifest": manifest.to_dict(),
                    "manifest_sha256": manifest.sha256(),
                }
                for manifest in self.list()
            ],
        }

    def save(self, path: Path) -> None:
        destination = path.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            self.snapshot(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(destination)

    @classmethod
    def load(cls, path: Path) -> AppRegistry:
        source = path.expanduser().resolve()
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid app registry JSON: {exc.msg}") from exc

        if not isinstance(payload, dict):
            raise ValueError("app registry must be an object")
        unknown = set(payload) - {"schema_version", "apps"}
        if unknown:
            raise ValueError(
                f"app registry contains unknown fields: {', '.join(sorted(unknown))}"
            )
        if payload.get("schema_version") != APP_REGISTRY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported app registry schema: {payload.get('schema_version')}")
        apps = payload.get("apps")
        if not isinstance(apps, list):
            raise ValueError("app registry apps must be an array")

        registry = cls()
        for index, entry in enumerate(apps):
            if not isinstance(entry, dict):
                raise ValueError(f"app registry entry {index} must be an object")
            unknown_entry = set(entry) - {"manifest", "manifest_sha256"}
            if unknown_entry:
                raise ValueError(
                    f"app registry entry {index} contains unknown fields: "
                    f"{', '.join(sorted(unknown_entry))}"
                )
            if set(entry) != {"manifest", "manifest_sha256"}:
                raise ValueError(f"app registry entry {index} is incomplete")
            manifest = AppManifest.from_dict(entry["manifest"])
            digest = entry["manifest_sha256"]
            if not isinstance(digest, str) or digest != manifest.sha256():
                raise ValueError(f"app registry entry {index} manifest digest mismatch")
            registry.register(manifest)
        return registry
