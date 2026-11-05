"""PhiOS Universal Shell R1: public-source-only catalog reader (no authority).

Read-only standard-library CLI. This does not import apps, touch installed
packages, grant shell permissions, or contact GitHub.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "phios.public-repo-catalog.v1"
DEFAULT = Path(__file__).with_name("public-repo-catalog.v1.json")
MAX_BYTES = 4 * 1024 * 1024
ID = re.compile(r"github:[0-9]{1,20}\Z")
OWNER = "MichaelWave369"


def _https_url(value: str, host: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return (
        parts.scheme == "https" and parts.hostname == host
        and not parts.username and not parts.password and not parts.port
        and not parts.query and not parts.fragment
    )


def read_catalog(path: Path = DEFAULT) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Catalog missing or beyond 4 MiB bound")
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict) or root.get("schema") != SCHEMA:
        raise ValueError("Unexpected catalog schema")
    proof = root.get("provenance")
    if not isinstance(proof, dict) or proof.get("owner") != OWNER or proof.get("scope") != "public":
        raise ValueError("Only public owner-scoped catalog is permitted")
    if proof.get("complete") is not True or not re.fullmatch(r"[0-9a-f]{40}", proof.get("source_blob_sha", "")):
        raise ValueError("Catalog lacks bounded snapshot evidence")
    policy = root.get("policy")
    if not isinstance(policy, dict) or policy != {
        "catalog_visibility": "public_source_only",
        "review_required": True,
        "automatic_install": False,
        "automatic_launch": False,
        "cross_platform_qualification": False,
    }:
        raise ValueError("Catalog cannot confer installation or launch authority")
    apps = root.get("apps")
    if not isinstance(apps, list) or len(apps) > 1000:
        raise ValueError("Invalid or oversized catalog")
    ids: set[str] = set()
    names: set[str] = set()
    for app in apps:
        if not isinstance(app, dict):
            raise ValueError("Invalid catalog entry")
        identifier = app.get("id")
        name = app.get("name")
        repository = app.get("repository")
        if not isinstance(identifier, str) or not ID.fullmatch(identifier):
            raise ValueError("Repository identity must be a stable public GitHub numeric ID")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
            raise ValueError("Repository name is invalid")
        if not _https_url(repository, "github.com") or urlsplit(repository).path != f"/{OWNER}/{name}":
            raise ValueError("Repository URL does not match public owner and name")
        if identifier in ids or name.lower() in names:
            raise ValueError("Duplicate repository identity")
        if app.get("availability") != "source_only":
            raise ValueError("Source metadata must not claim installability")
        if not isinstance(app.get("description"), str) or len(app["description"]) > 600:
            raise ValueError("Invalid description")
        if not isinstance(app.get("declared_homepage"), str) or len(app["declared_homepage"]) > 500:
            raise ValueError("Invalid declared homepage")
        if not isinstance(app.get("archived"), bool):
            raise ValueError("Invalid archive flag")
        ids.add(identifier)
        names.add(name.lower())
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read public PhiOS shell catalog (advisory, never installs)")
    parser.add_argument("--catalog", type=Path, default=DEFAULT)
    parser.add_argument("--search", default="", help="Optional name or description substring")
    parser.add_argument("--json", action="store_true", help="Print filtered public record JSON")
    args = parser.parse_args(argv)
    data = read_catalog(args.catalog)
    needle = args.search.casefold()
    found = [
        app for app in data["apps"]
        if needle in app["name"].casefold() or needle in app["description"].casefold()
    ]
    if args.json:
        print(json.dumps({"schema": SCHEMA, "source_blob_sha": data["provenance"]["source_blob_sha"],
                          "snapshot_fetched_at": data["provenance"]["snapshot_fetched_at"],
                          "count": len(found), "apps": found}, indent=2))
    else:
        print(f"PhiOS public catalog: {len(found)} / {len(data['apps'])} sources "
              f"(snapshot {data['provenance']['snapshot_fetched_at']})")
        for app in found:
            print(f"  {app['name']:34} {app['repository']}  [SOURCE ONLY]")
        print("No installs or launch authority. See phi-app profile-github for native appraisal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
