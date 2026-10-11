#!/usr/bin/env python3
"""Offline-first source census for PhiOS's *catalog*, never its app registry.

Default verifies the checked-in snapshot WITHOUT NETWORK. Explicit --refresh
retrieves only public repositories of the fixed founder GitHub account, never
clones code, infers executable entrypoints, or grants execution authority.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

OWNER = "MichaelWave369"
SCHEMA = "phios.public_ecosystem_catalog.v0.1"
SOURCE_SEARCH = "GITHUB_PUBLIC_REPOSITORY_SEARCH_SNAPSHOT"
SOURCE_API = "GITHUB_PUBLIC_OWNER_API_SNAPSHOT"
DEST = Path(__file__).resolve().parents[1] / "phishell/src/ecosystem/public-repos.json"
NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
MAX_REPOS = 2000
MAX_PAGES = 21


def make_entry(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("invalid public repo name")
    return {
        "name": name,
        "repository_url": f"https://github.com/{OWNER}/{name}",
        "kind": "source_catalog_entry",
        "availability": "SOURCE_ONLY",
        "installed": False,
        "launch_authorized": False,
        "redistribution_reviewed": False,
    }


def create_snapshot(names: list[str], *, source: str = SOURCE_API) -> dict[str, Any]:
    if source not in (SOURCE_SEARCH, SOURCE_API):
        raise ValueError("unsupported source")
    seen: set[str] = set()
    entries = []
    for name in sorted(names, key=lambda item: (item.casefold(), item)):
        entry = make_entry(name)
        key = name.casefold()
        if key in seen:
            raise ValueError("duplicate case-insensitive repository identity")
        seen.add(key)
        entries.append(entry)
    if not entries or len(entries) > MAX_REPOS:
        raise ValueError("invalid catalog size")
    return {
        "schema_version": SCHEMA,
        "owner": OWNER,
        "source": source,
        "snapshot_status": "OFFLINE_SOURCE_LISTING_ONLY",
        "entries": entries,
    }


def validate_snapshot(payload: Any) -> int:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "owner", "source", "snapshot_status", "entries"
    }:
        raise ValueError("unsupported catalog fields")
    if payload["schema_version"] != SCHEMA or payload["owner"] != OWNER:
        raise ValueError("wrong catalog schema/owner")
    if payload["snapshot_status"] != "OFFLINE_SOURCE_LISTING_ONLY":
        raise ValueError("catalog attempted to promote execution")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise ValueError("catalog entries missing")
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != set(make_entry("Valid").keys()):
            raise ValueError("invalid repo entry fields")
        if not isinstance(entry.get("name"), str):
            raise ValueError("invalid repo name type")
        if entry != make_entry(entry["name"]):
            raise ValueError("repo URL or grant fields mismatch")
        names.append(entry["name"])
    if payload != create_snapshot(names, source=payload["source"]):
        raise ValueError("catalog must be sorted and deterministic")
    return len(names)


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PhiOS-public-catalog-review/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("GitHub API did not return HTTP 200")
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("GitHub public listing page too large")
        return json.loads(data)


def collect_public_repositories(fetch: Callable[[str], Any] = _fetch_json) -> list[str]:
    names: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"https://api.github.com/users/{OWNER}/repos?per_page=100&page={page}&type=owner"
        rows = fetch(url)
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("invalid/incomplete GitHub public repositories response")
        if not rows:
            return names
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("owner"), dict):
                raise ValueError("invalid repo API record")
            if row["owner"].get("login") != OWNER:
                raise ValueError("foreign owner returned by API")
            if row.get("private") is not False:
                raise ValueError("unexpected private repository or absent visibility proof")
            name = row.get("name")
            entry = make_entry(name)
            if row.get("html_url") != entry["repository_url"]:
                raise ValueError("repository URL not canonical")
            names.append(name)
            if len(names) > MAX_REPOS:
                raise ValueError("catalog repository limit exceeded")
        if len(rows) < 100:
            return names
    raise ValueError("pagination did not reach a complete page boundary")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--refresh", action="store_true",
                       help="Explicitly query public GitHub API and rewrite source catalog")
    group.add_argument("--check", action="store_true",
                       help="Check bundled offline snapshot (default; no network)")
    args = parser.parse_args()
    if args.refresh:
        payload = create_snapshot(collect_public_repositories())
        count = validate_snapshot(payload)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        # Write only after the entire public API census has validated.
        temp = DEST.with_suffix(".json.tmp")
        try:
            temp.write_text(text, encoding="utf-8")
            temp.replace(DEST)
        finally:
            temp.unlink(missing_ok=True)
        print(f"PUBLIC_SOURCE_CATALOG_REFRESHED {count}, review changes before shipping")
    else:
        count = validate_snapshot(json.loads(DEST.read_text(encoding="utf-8")))
        print(f"PUBLIC_SOURCE_CATALOG_OFFLINE_VALID {count}; install/execution grants: NONE")


if __name__ == "__main__":
    main()
