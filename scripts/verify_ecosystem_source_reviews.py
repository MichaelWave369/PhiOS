#!/usr/bin/env python3
"""Fail-closed source-family review verification; never app readiness or authority."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.sync_public_ecosystem_catalog import DEST, OWNER, validate_snapshot

REVIEW_FILE = Path(__file__).resolve().parents[1] / "phishell/src/ecosystem/source-reviews.json"
SCHEMA = "phios.public_ecosystem_source_reviews.v0.1"
FAMILIES = frozenset({"OS_CORE", "LOCAL_SERVICE", "KNOWLEDGE_TOOL", "WEB_APP", "GAME", "XR_APP"})
ROW_KEYS = frozenset({
    "name", "source_sha", "family", "evidence_url", "review_basis",
    "offline_runnable_verified", "installed", "launch_authorized",
    "redistribution_reviewed",
})
NO_AUTHORITY = (
    "offline_runnable_verified", "installed", "launch_authorized",
    "redistribution_reviewed",
)
TOP_KEYS = frozenset({
    "schema_version", "source_catalog_owner", "default_family", "status", "reviews",
})


def validate_source_reviews(payload: Any, catalog: Any) -> int:
    validate_snapshot(catalog)
    if not isinstance(payload, dict) or set(payload) != TOP_KEYS:
        raise ValueError("unsupported source-review document fields")
    if (payload["schema_version"] != SCHEMA
            or payload["source_catalog_owner"] != OWNER
            or payload["default_family"] != "UNREVIEWED"
            or payload["status"] != "ADVISORY_SOURCE_CLASSIFICATION_ONLY"):
        raise ValueError("unsupported source-review contract or authority claim")
    reviews = payload["reviews"]
    if not isinstance(reviews, list) or len(reviews) > len(catalog["entries"]):
        raise ValueError("review list malformed or exceeds public catalog")
    public_names = {entry["name"] for entry in catalog["entries"]}
    names: list[str] = []
    for review in reviews:
        if not isinstance(review, dict) or set(review) != ROW_KEYS:
            raise ValueError("unexpected source-review fields")
        name = review["name"]
        sha = review["source_sha"]
        family = review["family"]
        if not isinstance(name, str) or name not in public_names:
            raise ValueError("review is not for an exact public catalog source")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            raise ValueError("source revision must be pinned")
        if not isinstance(family, str) or family not in FAMILIES:
            raise ValueError("unsupported source family")
        if review["evidence_url"] != (
            f"https://github.com/{OWNER}/{name}/blob/{sha}/README.md"
        ):
            raise ValueError("review evidence must point to pinned first-party README")
        if review["review_basis"] != "README_DECLARATION_ONLY":
            raise ValueError("source review cannot claim runtime verification")
        if any(review[key] is not False for key in NO_AUTHORITY):
            raise ValueError("source review attempted to mint availability or authority")
        names.append(name)
    if len(set(name.casefold() for name in names)) != len(names):
        raise ValueError("duplicate review identity")
    if names != sorted(names, key=lambda name: (name.casefold(), name)):
        raise ValueError("review entries are not deterministically ordered")
    return len(reviews)


def main() -> None:
    catalog = json.loads(DEST.read_text(encoding="utf-8"))
    payload = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    count = validate_source_reviews(payload, catalog)
    print(
        f"PHIOS_SOURCE_REVIEWS_VALID {count}; remaining "
        f"{len(catalog['entries']) - count} UNREVIEWED; "
        "offline/install/execution/redistribution claims: NONE"
    )


if __name__ == "__main__":
    main()
