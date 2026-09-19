import json
from pathlib import Path

import pytest

from phios.apps import AppManifest, AppRegistry


def _manifest_data(app_id: str = "phi.browsallax") -> dict[str, object]:
    return {
        "schema_version": "phios.app_manifest.v0.1",
        "app_id": app_id,
        "name": "Browsallax",
        "version": "0.1.0",
        "description": "Local-first browser and visual web studio.",
        "source": {
            "repository_url": "https://github.com/MichaelWave369/Browsallax",
            "license_expression": "MIT",
            "redistribution": "permitted",
        },
        "entrypoint": {
            "runtime": "node",
            "target": "package.json",
        },
        "permissions": ["network.local", "workspace.read"],
    }


def test_manifest_round_trip_and_digest_are_deterministic() -> None:
    manifest = AppManifest.from_dict(_manifest_data())
    encoded = manifest.canonical_json()
    restored = AppManifest.from_json(encoded)

    assert restored == manifest
    assert restored.sha256() == manifest.sha256()
    assert restored.to_dict()["permissions"] == ["network.local", "workspace.read"]


def test_manifest_unknown_fields_fail_closed() -> None:
    data = _manifest_data()
    data["surprise"] = True

    with pytest.raises(ValueError, match="unknown fields"):
        AppManifest.from_dict(data)


def test_relative_entrypoint_cannot_escape_app_root() -> None:
    data = _manifest_data()
    entrypoint = dict(data["entrypoint"])
    entrypoint["target"] = "../outside.py"
    data["entrypoint"] = entrypoint

    with pytest.raises(ValueError, match="parent segments"):
        AppManifest.from_dict(data)


def test_local_http_entrypoint_is_loopback_only() -> None:
    data = _manifest_data()
    data["entrypoint"] = {
        "runtime": "local_http",
        "target": "https://example.com/api",
    }

    with pytest.raises(ValueError, match="loopback-only"):
        AppManifest.from_dict(data)


def test_duplicate_permissions_are_rejected() -> None:
    data = _manifest_data()
    data["permissions"] = ["workspace.read", "workspace.read"]

    with pytest.raises(ValueError, match="duplicates"):
        AppManifest.from_dict(data)


def test_public_repository_does_not_imply_redistribution_permission() -> None:
    data = _manifest_data()
    source = dict(data["source"])
    source["license_expression"] = "NOASSERTION"
    source["redistribution"] = "unknown"
    data["source"] = source

    manifest = AppManifest.from_dict(data)

    assert manifest.source.repository_url.startswith("https://github.com/")
    assert manifest.source.redistribution == "unknown"


def test_registry_rejects_duplicate_app_ids_and_sorts_entries() -> None:
    registry = AppRegistry()
    second = AppManifest.from_dict(_manifest_data("phi.zeta"))
    first = AppManifest.from_dict(_manifest_data("phi.alpha"))

    registry.register(second)
    registry.register(first)

    assert [item.app_id for item in registry.list()] == ["phi.alpha", "phi.zeta"]

    with pytest.raises(ValueError, match="already registered"):
        registry.register(first)


def test_registry_save_load_and_digest_verification(tmp_path: Path) -> None:
    path = tmp_path / "apps.json"
    registry = AppRegistry()
    manifest = AppManifest.from_dict(_manifest_data())
    registry.register(manifest)
    registry.save(path)

    restored = AppRegistry.load(path)
    assert restored.get(manifest.app_id) == manifest
    assert restored.manifest_digest(manifest.app_id) == manifest.sha256()

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["apps"][0]["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        AppRegistry.load(path)
