"""Verify founder-proposed PhiOS application manifests without enrolling them.

Reads only committed JSON. Never fetches sources, installs packages, opens
browsers, writes a registry, or acquires any App Platform authority.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from phios.apps.manifest import AppManifest
from phios.apps.registry import AppRegistry
from scripts.sync_public_ecosystem_catalog import DEST as CATALOG_FILE, validate_snapshot

CANDIDATES = Path(__file__).resolve().parents[1] / "phishell/src/ecosystem/app-candidates.json"
SCHEMA = "phios.ecosystem_app_candidates.v0.1"
HEX40 = re.compile(r"^[a-f0-9]{40}$")
KEYS = {"app_key", "source_sha", "manifest", "source_build", "web", "review"}
BUILD_KEYS = {
    "working_directory", "command", "current_output_from_repo_root",
    "current_asset_base", "required_offline_asset_base",
    "build_verified_for_phios", "offline_dependency_closure_verified",
    "license_inventory_verified",
}
REVIEW_KEYS = {
    "state", "manifest_authoritative", "execution_authorized", "installed",
    "offline_bundle_verified", "desktop_launch_grant_verified", "external_done",
}
WEB_KEYS = {"url", "status"}
FIXED_SOURCES = {
    "vessie-web": (
        "https://github.com/MichaelWave369/SuperPhiVessel",
        "apps/vessie-web", "site/vessie",
        "https://michaelwave369.github.io/SuperPhiVessel/vessie/",
    ),
    "thinktank-web": (
        "https://github.com/MichaelWave369/think-tank",
        ".", "dist",
        "https://michaelwave369.github.io/think-tank/",
    ),
}


def inspect_candidates(payload: Any, catalog: Any) -> list[dict[str, str]]:
    validate_snapshot(catalog)
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "source_catalog_owner", "provenance", "candidates"
    }:
        raise ValueError("unsupported candidate envelope")
    if payload["schema_version"] != SCHEMA or payload["source_catalog_owner"] != "MichaelWave369":
        raise ValueError("unknown candidate schema/owner")
    if payload["provenance"] != "FOUNDER_REVIEW_CANDIDATE_PROPOSALS_NOT_EXECUTION_GRANTS":
        raise ValueError("candidate authority label altered")
    entries = payload["candidates"]
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("expected exactly two reviewed first-wave candidates")
    listed_sources = {e["repository_url"] for e in catalog["entries"]}
    registry = AppRegistry()  # purely ephemeral; never written to the installed registry
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != KEYS:
            raise ValueError("invalid candidate fields")
        key = entry["app_key"]
        if not isinstance(key, str) or key not in FIXED_SOURCES or key in seen:
            raise ValueError("unknown or duplicate candidate identity")
        seen.add(key)
        expected_repo, source_directory, output_directory, web_url = FIXED_SOURCES[key]
        commit = entry["source_sha"]
        if not isinstance(commit, str) or not HEX40.fullmatch(commit):
            raise ValueError("source must be pinned to a complete SHA-1")
        manifest = AppManifest.from_dict(entry["manifest"])
        if manifest.app_id != f"phios.{key}" or manifest.source.repository_url != expected_repo:
            raise ValueError("candidate manifest identity mismatch")
        if manifest.source.repository_url not in listed_sources:
            raise ValueError("proposed app is not in public source snapshot")
        if manifest.version != "0.1.0" or manifest.source.license_expression != "MIT":
            raise ValueError("unexpected version or declared license")
        if manifest.source.redistribution != "unknown":
            raise ValueError("license review must remain separate from public visibility")
        if manifest.entrypoint.runtime != "static_web" or manifest.entrypoint.target != "index.html":
            raise ValueError("unreviewed candidate entrypoint")
        if manifest.permissions != ():
            raise ValueError("undeclared permission request")
        build = entry["source_build"]
        if not isinstance(build, dict) or set(build) != BUILD_KEYS:
            raise ValueError("invalid source-build review fields")
        if build["working_directory"] != source_directory or build["current_output_from_repo_root"] != output_directory:
            raise ValueError("wrong source tree / emitted directory")
        if build["command"] != ["npm", "run", "build"]:
            raise ValueError("unexpected build command")
        if build["current_asset_base"] != (
            "/SuperPhiVessel/vessie/" if key == "vessie-web" else "/"
        ):
            raise ValueError("unexpected upstream asset base")
        if build["required_offline_asset_base"] != "/":
            raise ValueError("offline PhiOS asset-base goal must be root-relative")
        if any(build[x] is not False for x in (
            "build_verified_for_phios", "offline_dependency_closure_verified",
            "license_inventory_verified"
        )):
            raise ValueError("build evidence cannot be self-promoted")
        web = entry["web"]
        if not isinstance(web, dict) or set(web) != WEB_KEYS or web != {
            "url": web_url, "status": "PUBLIC_SITE_LINK_ONLY"
        }:
            raise ValueError("web link must be reviewed and non-executing")
        if urlsplit(web["url"]).scheme != "https":
            raise ValueError("public site must be HTTPS")
        review = entry["review"]
        if not isinstance(review, dict) or set(review) != REVIEW_KEYS:
            raise ValueError("review field mismatch")
        if review["state"] != "HELD_FOR_OPERATOR_REVIEW" or any(
            review[field] is not False for field in REVIEW_KEYS - {"state"}
        ):
            raise ValueError("candidate attempted to assert installation, approval or DONE")
        registry.register(manifest)  # checksum and duplicate-ID checking, not a persisted grant
        output.append({"key": key, "manifest_sha256": manifest.sha256(), "source_sha": commit})
    if seen != set(FIXED_SOURCES):
        raise ValueError("candidate set changed")
    return output


def main() -> None:
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    verified = inspect_candidates(candidates, catalog)
    print("PHIOS_APP_CANDIDATES_REVIEW_ONLY_VALID", json.dumps(verified, sort_keys=True))


if __name__ == "__main__":
    main()
