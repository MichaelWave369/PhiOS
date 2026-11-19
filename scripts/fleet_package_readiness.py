"""Project public source readiness into PhiOS and Trellis preflight data.

Profiles declare obligations. Install, launch and distribution still use the
existing exact artifact, review and execution contracts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_ecosystem_app_candidates import (
    CANDIDATES, CATALOG_FILE, inspect_candidates,
)

PROFILES = CANDIDATES.with_name("fleet-readiness.json")
SCHEMA = "phios.fleet_readiness.v1"
OWNER = "MichaelWave369"
KINDS = {"application", "library", "service", "research", "documentation"}
SHA = re.compile(r"[a-f0-9]{40}\Z")
FIELDS = {"repository", "repository_id", "source_sha", "kind", "required_tests",
          "build_artifact", "integration", "distribution", "human_acceptance"}


def require(condition, reason):
    if not condition:
        raise ValueError("FLEET_READINESS_" + reason)


def labels(value):
    return (isinstance(value, list) and 1 <= len(value) <= 12 and
            all(isinstance(v, str) and 0 < len(v) <= 240 for v in value) and
            len(set(value)) == len(value))


def inspect_profiles(payload, catalog, candidates):
    inspect_candidates(candidates, catalog)
    require(isinstance(payload, dict) and set(payload) == {"schema_version", "owner", "profiles"} and
            payload["schema_version"] == SCHEMA and payload["owner"] == OWNER and
            isinstance(payload["profiles"], list) and 0 < len(payload["profiles"]) <= 100,
            "ENVELOPE")
    public = {OWNER + "/" + entry["name"] for entry in catalog["entries"]}
    apps = {app["app_key"]: app for app in candidates["candidates"]}
    result, ids, app_keys = {}, set(), set()
    for row in payload["profiles"]:
        require(isinstance(row, dict) and set(row) == FIELDS, "PROFILE_FIELDS")
        name, rid = row["repository"], row["repository_id"]
        require(isinstance(name, str) and name in public and name not in result and
                type(rid) is int and 0 < rid <= 9007199254740991 and rid not in ids and
                isinstance(row["source_sha"], str) and SHA.fullmatch(row["source_sha"]),
                "PUBLIC_SOURCE_IDENTITY")
        require(isinstance(row["kind"], str) and row["kind"] in KINDS and
                labels(row["required_tests"]) and labels(row["human_acceptance"]),
                "ACCEPTANCE_OR_TEST_REQUIREMENTS")
        integration, artifact = row["integration"], row["build_artifact"]
        require(isinstance(integration, dict) and set(integration) == {"status", "candidate"},
                "INTEGRATION_FIELDS")
        key = integration["candidate"]
        if key is not None:
            require(isinstance(key, str) and key in apps and key not in app_keys and
                    row["kind"] == "application" and integration["status"] == "staging_only" and
                    row["distribution"] == "held", "UNREVIEWED_INTEGRATION_OR_DISTRIBUTION")
            app = apps[key]
            require(app["source_sha"] == row["source_sha"] and
                    app["manifest"]["source"]["repository_url"] == "https://github.com/" + name and
                    artifact == {"path": app["source_build"]["current_output_from_repo_root"],
                                 "sha256": None}, "CANDIDATE_BUILD_IDENTITY_DRIFT")
            app_keys.add(key)
        else:
            require(integration["status"] == "out_of_scope" and
                    artifact is None and row["distribution"] == "not_requested",
                    "UNREVIEWED_DISTRIBUTION_REQUEST")
        result[name] = row
        ids.add(rid)
    require(app_keys == set(apps), "MISSING_STAGING_PROFILE")
    return result


def catalog_projection(catalog, profiles):
    for entry in catalog["entries"]:
        repo = OWNER + "/" + entry["name"]
        yield profiles.get(repo) or {
            "repository": repo, "repository_id": None, "source_sha": None, "kind": None,
            "required_tests": [], "build_artifact": None,
            "integration": {"status": "profile_required", "candidate": None},
            "distribution": "held", "human_acceptance": ["Review repository type and delivery requirements."],
        }


def load_profiles(catalog, candidates):
    return inspect_profiles(json.loads(PROFILES.read_text(encoding="utf-8")), catalog, candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="Exact public owner/name. Omit to report the whole catalog.")
    args = parser.parse_args()
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    rows = list(catalog_projection(catalog, load_profiles(catalog, candidates)))
    if args.repo:
        rows = [row for row in rows if row["repository"] == args.repo]
        require(bool(rows), "REPOSITORY_NOT_IN_PUBLIC_CATALOG")
    print(json.dumps({"schema_version": SCHEMA, "owner": OWNER, "profiles": rows}, indent=2))


if __name__ == "__main__":
    main()
