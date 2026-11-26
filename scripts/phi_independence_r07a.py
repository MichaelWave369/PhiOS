"""R07-A: correlate private field receipts; never issue EXIT-VERIFIED."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "phios.independence.field.v1"
MAX = 2 * 1024 * 1024
HEX = re.compile(r"[a-f0-9]{64}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
REPOS = ("PhiOS", "PhiBuddy", "Agentora")
GATES = {
    "wan_denied": ("wan-observation.json",),
    "readiness": ("r01.json",),
    "vault_restore": ("vault-verify.json", "vault-restore.json", "restore-observation.json"),
    "inference": ("r03.json",),
    "bridge": ("r04b.json",),
    "forge": ("r05b.json", "r05a-plan.json", "r05a.json"),
    "mesh": ("r06a.json", "r06b-submit.json", "r06b-restart.json"),
    "cold_recovery": ("cold-observation.json",),
    "exit_rights": ("exit-observation.json",),
}
FILES = tuple(name for names in GATES.values() for name in names)
MANUAL = {
    "wan-observation.json": ("both_hosts_wan_denied", "lan_and_loopback_available",
                             "no_cloud_credentials_used", "negative_external_probe"),
    "restore-observation.json": ("fresh_compatible_environment", "read_without_phi_account",
                                 "original_and_restored_bytes_compared"),
    "cold-observation.json": ("both_hosts_cold_restarted", "archive_read_after_restart",
                              "mesh_journal_preserved", "no_duplicate_admission_observed"),
    "exit-observation.json": ("representative_dataset_complete_for_declared_scope",
                              "replacement_local_model_exercised",
                              "old_optional_credentials_revoked",
                              "documented_independent_read_and_restore"),
}


def canonical(value):
    # Agentora's autonomous-turn canonical JSON uses UTF-8; its bridge uses
    # ASCII escaping. For the bridge review digest use its exact convention below.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(condition, code):
    if not condition:
        raise ValueError(code)


def hex64(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def hex40(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def unique(pairs):
    result = {}
    for k, v in pairs:
        check(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def bad_constant(_):
    raise ValueError("NONFINITE_JSON")


def read(path):
    check(path.is_file() and not path.is_symlink(), "FILE_MISSING_OR_UNSAFE")
    with path.open("rb") as handle:
        raw = handle.read(MAX + 1)
    check(0 < len(raw) <= MAX, "FILE_SIZE")
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=bad_constant)
    check(type(value) is dict, "OBJECT_REQUIRED")
    return raw, value


def private_root(root):
    root = Path(root)
    check(root.is_dir() and not root.is_symlink(), "PRIVATE_DIRECTORY_REQUIRED")
    root = root.resolve()
    check(not any((p / ".git").exists() for p in (root, *root.parents)),
          "GIT_DESTINATION_REFUSED")
    return root


def template():
    return {"schema": SCHEMA, "campaign_id": "", "observed_utc": "",
            "scope": "synthetic-independent-workspace-pilot",
            "observer": "", "source_commits": {repo: "" for repo in REPOS},
            "versions": {"primary_os": "", "secondary_os": "", "python": "",
                         "ollama": "", "docker": "", "model_tags": ""},
            "gates": {gate: {"observation": "NOT_RUN", "artifacts": {
                name: "" for name in names}} for gate, names in GATES.items()}}


def inventory(root):
    root = private_root(root)
    entries = {}
    for name in FILES:
        try:
            raw, _ = read(root / name)
            entries[name] = sha(raw)
        except (ValueError, OSError, RecursionError):
            entries[name] = None
    return {"schema": SCHEMA, "artifact_sha256": entries,
            "note": "File inventory only; no observation or approval inferred."}


def manual(name, data):
    expected = {"schema", "observed_utc", "checks", "method", "observer"}
    if name == "restore-observation.json":
        expected |= {"original_sha256", "restored_sha256"}
    check(set(data) == expected and data["schema"] == "phios.field-observation.v1",
          "MANUAL_SCHEMA")
    timestamp(data["observed_utc"])
    check(all(isinstance(data[k], str) and 0 < len(data[k].strip()) <= 2000
              for k in ("method", "observer")), "MANUAL_DETAIL")
    check(type(data["checks"]) is dict and set(data["checks"]) == set(MANUAL[name])
          and all(v is True for v in data["checks"].values()), "MANUAL_NOT_ALL_OBSERVED")


def timestamp(value):
    check(isinstance(value, str) and len(value) <= 40, "TIMESTAMP")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    check(parsed.tzinfo is not None and parsed.utcoffset() is not None
          and parsed <= datetime.now(timezone.utc), "TIMESTAMP")


def no_authority(data, keys):
    check(all(data.get(key) is False for key in keys), "AUTHORITY_OR_ATTESTATION")


def correlate(gate, data):
    for name, value in data.items():
        if name in MANUAL:
            manual(name, value)
    if gate == "readiness":
        r = data["r01.json"]
        check(r.get("schema") == 1 and r.get("certification") == "UNVERIFIED"
              and r.get("operator_declared_offline") is True
              and r.get("offline_verified") is False
              and r.get("inference") == {"status": "PASS", "scope": "loopback_marker_only"},
              "READINESS_MARKER")
    elif gate == "vault_restore":
        v, r, o = (data[n] for n in GATES[gate])
        check(v.get("status") == "INTEGRITY_VERIFIED" and r.get("status") == "RESTORED"
              and v.get("schema") == r.get("schema") == 1
              and hex64(v.get("sha256")) and v["sha256"] == r.get("sha256")
              == o.get("original_sha256") == o.get("restored_sha256")
              and type(v.get("nodes")) is int and v["nodes"] > 0
              and r.get("nodes") == v["nodes"], "VAULT_RESTORE_MISMATCH")
    elif gate == "inference":
        r = data["r03.json"]
        check(r.get("suite") == "phi-inference-smoke-v1" and r.get("schema") == 1
              and r.get("complete") is True and r.get("operator_declared_offline") is True,
              "INFERENCE_INCOMPLETE")
        no_authority(r, ("offline_verified", "routing_authority"))
        repeats, reports = r.get("repeats"), r.get("reports")
        check(type(repeats) is int and 1 <= repeats <= 3 and type(reports) is list
              and 2 <= len(reports) <= 3, "INFERENCE_COMPARISON_REQUIRED")
        cases = {"arithmetic", "ordering", "logic", "extraction", "code_trace", "instruction"}
        models = set()
        for report in reports:
            model, rows = report["model"], report["attempts"]
            check(isinstance(model, str) and ":" in model and "cloud" not in model.lower()
                  and model not in models and type(rows) is list
                  and len(rows) == 6 * repeats, "INFERENCE_MODEL_OR_ROWS")
            models.add(model)
            keys = set()
            for row in rows:
                check(row["case"] in cases and type(row["repeat"]) is int
                      and 1 <= row["repeat"] <= repeats
                      and row["status"] in {"CORRECT", "INCORRECT"}
                      and row["correct"] is (row["status"] == "CORRECT"),
                      "INFERENCE_ATTEMPT")
                keys.add((row["repeat"], row["case"]))
            correct = sum(row["correct"] for row in rows)
            check(len(keys) == 6 * repeats and report["correct"] == correct
                  and report["attempted"] == report["expected_attempts"] == len(rows)
                  and report["errors"] == 0 and correct > 0
                  and report["exact_match_fraction"] == correct / len(rows),
                  "INFERENCE_COUNTS")
    elif gate == "bridge":
        r = data["r04b.json"]
        check(r.get("schema") == "agentora.phibuddy-review-receipt.v1"
              and r.get("state") == "LOCAL_REVIEW_UNVERIFIED"
              and all(hex64(r.get(k)) for k in ("consent_sha256", "packet_sha256", "review_sha256"))
              and r.get("human_review_required") is True and type(r.get("tool_calls")) is int
              and r["tool_calls"] == 0, "BRIDGE_RECEIPT")
        no_authority(r, ("execution_authority", "source_verified", "completion_verified",
                         "model_identity_attested", "offline_verified", "persisted_by_bridge"))
        review = r.get("review")
        check(type(review) is dict and set(review) == {"assessment", "risks", "next_steps", "uncertainties"}
              and all(isinstance(v, str) and 0 < len(v.strip()) <= 3000 for v in review.values()),
              "BRIDGE_REVIEW")
        check(sha(json.dumps(review, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("ascii"))
              == r["review_sha256"], "BRIDGE_REVIEW_DIGEST")
    elif gate == "forge":
        p, wrapper, b = (data[n] for n in GATES[gate])
        check(p.get("schema") == "agentora.phiforge.r05b.v1"
              and p.get("state") == "CANDIDATE_REVIEW_REQUIRED"
              and b.get("schema") == "agentora.phiforge.r05a.v1"
              and b.get("state") == "BUILD_PASS_REVIEW_ONLY" and type(b.get("exit_code")) is int
              and b["exit_code"] == 0, "FORGE_STATE")
        no_authority(p, ("build_authorized", "eligible_for_merge", "execution_authority", "offline_verified"))
        no_authority(b, ("eligible_for_merge", "execution_authority", "offline_verified"))
        plan = wrapper["plan"]
        check(p.get("operator_declared_offline") is True
              and b.get("operator_declared_offline") is True
              and b.get("network_none_requested") is True and b.get("pull_never_requested") is True
              and plan.get("schema") == "agentora.phiforge.r05a.v1"
              and plan.get("state") == "REVIEW_REQUIRED", "FORGE_BUILD_BOUNDARY")
        check(hex64(b.get("plan_sha256")) and b["plan_sha256"] == wrapper.get("plan_sha256")
              and b["plan_sha256"] == sha(canonical(plan))
              and p.get("plan_sha256") == sha(canonical(p["plan"])), "FORGE_PLAN_DIGEST")
        check(hex40(b.get("source_sha")) and b["source_sha"] == plan["task"]["source_sha"]
              == p["plan"]["task"]["source_sha"] and plan["task"] == p["plan"]["task"]
              and isinstance(b.get("image_id"), str) and b["image_id"].startswith("sha256:")
              and hex64(b["image_id"][7:]) and b["image_id"] == plan["image_id"], "FORGE_SOURCE_IMAGE")
        for key in ("patch_sha256", "after_sha256"):
            check(hex64(b.get(key)) and b[key] == p["proposal"][key] == plan["proposal"][key],
                  "FORGE_PATCH_MISMATCH")
        check(p["proposal"]["patch"] == plan["proposal"]["patch"]
              and sha(p["proposal"]["patch"].encode("utf-8")) == b["patch_sha256"],
              "FORGE_PATCH_DIGEST")
    elif gate == "mesh":
        a, b, restarted = (data[n] for n in GATES[gate])
        check(a.get("schema") == "phios.mesh.challenge.v1"
              and a.get("state") == "PINNED_PEER_CHALLENGE_PASSED"
              and a.get("tls_pin_verified") is True and a.get("rounds") == 369
              and hex64(a.get("nonce")), "MESH_TLS_CHALLENGE")
        no_authority(a, ("execution_authority", "inference_verified",
                         "offline_verified", "remote_workload_authorized"))
        value = bytes.fromhex(a["nonce"])
        for _ in range(369):
            value = hashlib.sha256(value).digest()
        check(value.hex() == a.get("result_sha256"), "MESH_CHALLENGE_DIGEST")
        check(b == restarted and b.get("schema") == "phios.mesh.inference.v1"
              and b.get("state") == "FINISHED" and b.get("outcome") == "CORRECT"
              and b.get("node") == a.get("node") and hex64(b.get("job")), "MESH_RESTART_RESULT")
        no_authority(b, ("model_identity_attested", "offline_verified", "execution_authority"))
        spec = {"schema": b["schema"], "job": b["job"], "node": b["node"],
                "model": b["model_requested"], "case": b["case"]}
        check(b.get("task_sha256") == sha(canonical(spec)), "MESH_TASK_DIGEST")


def evaluate(root, manifest):
    root = private_root(root)
    check(set(manifest) == set(template()) and manifest["schema"] == SCHEMA
          and manifest["scope"] == "synthetic-independent-workspace-pilot", "MANIFEST_SCHEMA")
    check(isinstance(manifest["campaign_id"], str)
          and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", manifest["campaign_id"])
          and isinstance(manifest["observer"], str) and 0 < len(manifest["observer"].strip()) <= 200,
          "CAMPAIGN_IDENTITY")
    timestamp(manifest["observed_utc"])
    commits, versions = manifest["source_commits"], manifest["versions"]
    check(type(commits) is dict and set(commits) == set(REPOS)
          and all(hex40(v) for v in commits.values()), "SOURCE_COMMITS")
    check(type(versions) is dict and set(versions) == set(template()["versions"])
          and all(isinstance(v, str) and 0 < len(v.strip()) <= 300 for v in versions.values()),
          "VERSIONS_REQUIRED")
    gates = manifest["gates"]
    check(type(gates) is dict and set(gates) == set(GATES), "GATE_INVENTORY")
    results = {}
    for gate, names in GATES.items():
        try:
            entry = gates[gate]
            check(type(entry) is dict and set(entry) == {"observation", "artifacts"}
                  and entry["observation"] in {"NOT_RUN", "FAIL", "OBSERVED_PASS"},
                  "GATE_SCHEMA")
            check(type(entry["artifacts"]) is dict and set(entry["artifacts"]) == set(names),
                  "ARTIFACT_INVENTORY")
            check(entry["observation"] == "OBSERVED_PASS", "FIELD_OBSERVATION_NOT_PASS")
            data = {}
            for name in names:
                expected = entry["artifacts"][name]
                check(hex64(expected), "ARTIFACT_HASH_MISSING")
                raw, value = read(root / name)
                check(sha(raw) == expected, "ARTIFACT_HASH_MISMATCH")
                data[name] = value
            correlate(gate, data)
            results[gate] = {"state": "CORRELATED_SELF_REPORTED"}
        except (ValueError, KeyError, TypeError, AttributeError, OSError, RecursionError) as exc:
            # Never print private paths or arbitrary values from the artifacts.
            code = str(exc) if type(exc) is ValueError and re.fullmatch(r"[A-Z_]+", str(exc)) else "INVALID_OR_MISSING_EVIDENCE"
            results[gate] = {"state": "HELD", "reason": code}
    count = sum(r["state"] == "CORRELATED_SELF_REPORTED" for r in results.values())
    return {"schema": SCHEMA, "state": "REVIEW_READY_NOT_CERTIFIED" if count == len(GATES) else "HELD",
            "sovereignty_status": "PARTIAL" if count else "UNVERIFIED",
            "correlated_gates": count, "required_gates": len(GATES), "gates": results,
            "offline_verified": False, "independent_review_verified": False,
            "source_commits_verified": False, "exit_verified": False, "authority_granted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "inventory", "review"))
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.stage == "template":
            result = template()
        elif args.directory is None:
            raise ValueError("directory required")
        elif args.stage == "inventory":
            result = inventory(args.directory)
        else:
            root = private_root(args.directory)
            _, manifest = read(root / "campaign.json")
            result = evaluate(root, manifest)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 1 if result.get("state") == "HELD" else 0
    except (ValueError, OSError, TypeError, RecursionError):
        print("FIELD_HELD: invalid private directory or campaign manifest", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
