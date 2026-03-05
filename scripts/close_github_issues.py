#!/usr/bin/env python3
"""Close cgcardona issues with resolution comments via GitHub API."""

from __future__ import annotations

import os
import sys
from typing import TypedDict

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

REPO = "MichaelWave369/PhiOS"
API_BASE = f"https://api.github.com/repos/{REPO}/issues"


class IssueResolution(TypedDict):
    title: str
    body: str


ISSUE_RESOLUTIONS: dict[int, IssueResolution] = {
    2: {
        "title": "Shell passthrough hardening",
        "body": (
            "@cgcardona Thanks Gabriel — this is now resolved in v0.3. "
            "Fallback command execution now uses safe argument parsing and never uses shell=True. "
            "Coverage: tests/test_v03_hardening.py::test_shell_passthrough_uses_no_shell_true "
            "and ::test_shell_passthrough_safe_with_special_chars."
        ),
    },
    3: {
        "title": "Sovereign path traversal guard",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3. "
            "Snapshot path resolution now validates traversal and rejects unsafe relative escapes. "
            "Coverage: tests/test_v03_hardening.py::test_sovereign_export_rejects_path_traversal "
            "and ::test_sovereign_verify_rejects_path_traversal."
        ),
    },
    4: {
        "title": "Exception style cleanup",
        "body": (
            "@cgcardona Thanks Gabriel — resolved in v0.3 with anti-pattern cleanup and stricter handling. "
            "Coverage includes a repository scan test for bare exceptions in runtime code."
        ),
    },
    5: {
        "title": "Documentation expansion",
        "body": (
            "@cgcardona Thanks Gabriel — addressed in v0.3. README and module docs were expanded "
            "with install, usage, and security posture details."
        ),
    },
    6: {
        "title": "TypedDict public schemas",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3. Public result schemas now use TypedDict for coherence "
            "and sovereignty payloads. Coverage: tests/test_v03_hardening.py::test_lt_result_uses_typeddict "
            "and ::test_snapshot_uses_typeddict."
        ),
    },
    7: {
        "title": "Coverage broadening",
        "body": (
            "@cgcardona Thanks Gabriel — resolved with expanded hardening tests and CI checks in v0.3. "
            "The suite now covers security, typing, caching, and sync degradation paths."
        ),
    },
    8: {
        "title": "Ollama availability cache",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3 with a TTL cache around Ollama availability checks. "
            "Coverage: tests/test_v03_hardening.py::test_ollama_check_cached_within_ttl and "
            "::test_ollama_cache_refreshes_after_ttl."
        ),
    },
    9: {
        "title": "Tooling alignment",
        "body": (
            "@cgcardona Thanks Gabriel — resolved in v0.3 by aligning packaging/tooling and adding ruff + mypy "
            "in CI with local-first policy checks preserved."
        ),
    },
    10: {
        "title": "Version single source of truth",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3. Version now comes from phios.__version__ only, "
            "with dynamic packaging metadata. Coverage: tests/test_v03_hardening.py::test_version_single_source_of_truth "
            "and ::test_version_matches_pyproject."
        ),
    },
    11: {
        "title": "Display module cleanup",
        "body": (
            "@cgcardona Thanks Gabriel — resolved in v0.3 with display helper cleanup and reserved markers "
            "for staged future work."
        ),
    },
    12: {
        "title": "Configurable Ollama URL",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3. OLLAMA_URL is now env-configurable with localhost default. "
            "Coverage: tests/test_v03_hardening.py::test_ollama_url_reads_from_environment "
            "and ::test_ollama_url_defaults_to_localhost."
        ),
    },
    13: {
        "title": "Repository hygiene ignores",
        "body": (
            "@cgcardona Thanks Gabriel — fixed in v0.3 with expanded ignore rules for common build/cache/editor artifacts."
        ),
    },
}


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }


def _request(method: str, url: str, token: str, payload: dict | None = None):
    if requests is None:
        raise RuntimeError("requests is not installed; install dev dependencies first")
    return requests.request(method=method, url=url, headers=_headers(token), json=payload, timeout=15)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Missing GITHUB_TOKEN. Example:\n  export GITHUB_TOKEN=ghp_xxx\n  python scripts/close_github_issues.py")
        return 1

    closed = 0
    total = len(ISSUE_RESOLUTIONS)

    for issue_number, resolution in ISSUE_RESOLUTIONS.items():
        issue_url = f"{API_BASE}/{issue_number}"
        comment_url = f"{issue_url}/comments"

        print(f"Processing issue #{issue_number}: {resolution['title']}")

        try:
            comment_resp = _request("POST", comment_url, token, {"body": resolution["body"]})
            if comment_resp.status_code >= 400:
                print(f"  comment failed ({comment_resp.status_code}): {comment_resp.text[:180]}")
            else:
                print("  comment posted")
        except Exception as exc:  # noqa: BLE001
            print(f"  comment error: {exc}")

        try:
            get_resp = _request("GET", issue_url, token)
            if get_resp.status_code >= 400:
                print(f"  issue lookup failed ({get_resp.status_code}): {get_resp.text[:180]}")
                continue
            state = get_resp.json().get("state", "open")
            if state == "closed":
                print("  already closed")
                closed += 1
                continue

            close_resp = _request("PATCH", issue_url, token, {"state": "closed"})
            if close_resp.status_code >= 400:
                print(f"  close failed ({close_resp.status_code}): {close_resp.text[:180]}")
                continue
            print("  closed")
            closed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  close error: {exc}")

    print(f"✓ {closed}/{total} issues closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
