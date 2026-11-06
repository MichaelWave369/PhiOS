"""R4 reviewed browser-app registry: evidence descriptors, never install grants.

This reader has no network calls and no side effects. The only R4 release
candidate is PhiOS Web's same-origin PWA, with Chromium CI evidence. Production
reachability and browser-managed installation are *not* asserted by this file.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlsplit

from shell_catalog_v1 import read_catalog

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "app-center-reviews.v1.json"

POLICY = {
    "source_listing_is_not_installation": True,
    "autonomous_installs": False,
    "native_install_grants": False,
    "user_gesture_required": True,
    "browser_controls_pwa_install": True,
}
ALLOWED_APP = "github:1442243366"
PROFILE_KEYS = {
    "app_id", "name", "repository", "runtime", "review_status", "launch_url",
    "scope_path", "evidence", "actions", "disclosure",
}
EVIDENCE_KEYS = {
    "repository", "test_path", "source_pr", "ci_basis",
    "evidence_scope", "live_endpoint_independently_verified",
}
ACTION_KEYS = {"open", "install", "native_install", "automatic_execution"}


def read_reviews(path: Path = REGISTRY) -> dict:
    if not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError("Registry missing or exceeds 128 KiB")
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict) or set(root) != {
        "schema", "catalog_source_sha", "policy", "reviewed_web_apps"
    } or root["schema"] != "phios.app-center-reviews.v1":
        raise ValueError("Unknown review registry schema")
    catalog = read_catalog()
    if root["catalog_source_sha"] != catalog["provenance"]["source_blob_sha"]:
        raise ValueError("Catalog snapshot mismatch")
    if root["policy"] != POLICY:
        raise ValueError("Registry cannot grant automatic or native install authority")
    items = root["reviewed_web_apps"]
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError("R4 requires exactly one explicitly reviewed candidate")
    entry = items[0]
    if not isinstance(entry, dict) or set(entry) != PROFILE_KEYS:
        raise ValueError("Profile has missing or unauthorized fields")
    matched = next((x for x in catalog["apps"] if x["id"] == entry["app_id"]), None)
    if not matched or entry["app_id"] != ALLOWED_APP or entry["name"] != "PhiOS Web" or (
        entry["repository"] != matched["repository"]):
        raise ValueError("App profile does not match approved public source identity")
    if (entry["runtime"], entry["review_status"], entry["scope_path"]) != (
        "browser_pwa", "ci_reviewed_browser_app", "/os/"
    ):
        raise ValueError("Only CI-reviewed browser PWA may appear in R4")
    url = urlsplit(entry["launch_url"])
    if (url.scheme != "https" or url.netloc != "phi-field.com" or url.path != "/os/"
        or url.query or url.fragment or url.username or url.password):
        raise ValueError("Launch URL must be exact first-party PWA entry point")
    evidence = entry["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS or (
        evidence["repository"] != "MichaelWave369/phi-field" or
        evidence["test_path"] != "tests/browser_web_os.py" or
        type(evidence["source_pr"]) is not int or evidence["source_pr"] != 8 or
        evidence["evidence_scope"] != "static_build_and_chromium_ci" or
        evidence["live_endpoint_independently_verified"] is not False or
        not isinstance(evidence["ci_basis"], str) or not evidence["ci_basis"]
    ):
        raise ValueError("Untrusted or inflated CI evidence")
    actions = entry["actions"]
    if not isinstance(actions, dict) or set(actions) != ACTION_KEYS or actions != {
        "open": "explicit_navigation",
        "install": "browser_mediated_if_available",
        "native_install": False,
        "automatic_execution": False,
    }:
        raise ValueError("Review must not grant installation, execution or launch")
    if not isinstance(entry["disclosure"], str) or not entry["disclosure"]:
        raise ValueError("Missing browser/authority disclosure")
    return root


def main() -> int:
    data = read_reviews()
    entry = data["reviewed_web_apps"][0]
    print(f"PhiOS App Center: 1 CI-reviewed browser PWA, {len(read_catalog()['apps']) - 1}"
          f" source-only projects. Candidate: {entry['launch_url']}. "
          "Production reachability unverified; install belongs to browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
