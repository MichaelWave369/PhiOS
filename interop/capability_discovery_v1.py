"""Source-only capability discovery; not a runtime manifest, router or grant."""
import argparse
import json
from pathlib import Path
import re

SCHEMA = "phios.capability-discovery.v1"
ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "phishell/src/ecosystem/public-repos.json"
DECLARATIONS = ROOT / "interop/capability-discovery.v1.json"
TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,95}")
REPO = re.compile(r"https://github\.com/MichaelWave369/[A-Za-z0-9_.-]{1,100}")
REVISION = re.compile(r"[0-9a-f]{40}")
PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
FIELDS = set("id repository revision capability input_contract output_contract mode evidence limitations latency_ms memory_mib authority".split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    with Path(path).open("rb") as source:
        data = source.read(2_000_001)
    require(len(data) <= 2_000_000, "Input too large")
    return json.loads(data, object_pairs_hook=unique)


def public_repositories(catalog):
    require(isinstance(catalog, dict) and catalog.get("owner") == "MichaelWave369"
            and isinstance(catalog.get("entries"), list), "Invalid public catalog")
    entries = catalog["entries"]
    require(len(entries) <= 10000, "Catalog too large")
    result = set()
    for row in entries:
        require(isinstance(row, dict) and isinstance(row.get("repository_url"), str)
                and REPO.fullmatch(row["repository_url"]) and row.get("kind") == "source_catalog_entry"
                and row.get("availability") == "SOURCE_ONLY" and row.get("installed") is False
                and row.get("launch_authorized") is False and row.get("redistribution_reviewed") is False,
                "Invalid public catalog record")
        url = row["repository_url"]
        require(url.lower() not in result, "Duplicate public repository")
        result.add(url.lower())
    return result


def validate(declarations, catalog):
    """Validate declared source shapes; never authenticate source claims or hosts."""
    require(isinstance(declarations, dict) and set(declarations) == {"schema", "authority", "entries"}
            and declarations["schema"] == SCHEMA and declarations["authority"] == "NONE"
            and isinstance(declarations["entries"], list) and len(declarations["entries"]) <= 1024,
            "Invalid declaration catalog")
    public = public_repositories(catalog)
    seen = set()
    for row in declarations["entries"]:
        require(isinstance(row, dict) and set(row) == FIELDS, "Unexpected declaration fields")
        require(all(is_token(row[key]) for key in ("id", "capability", "input_contract", "output_contract")),
                "Invalid capability identifier")
        require(row["id"] not in seen, "Duplicate declaration")
        seen.add(row["id"])
        require(isinstance(row["repository"], str) and REPO.fullmatch(row["repository"])
                and row["repository"].lower() in public and isinstance(row["revision"], str)
                and REVISION.fullmatch(row["revision"]), "Uncataloged or unpinned source")
        require(row["mode"] in ("synthetic", "opt-in-local") and row["authority"] == "NONE"
                and row["latency_ms"] is None and row["memory_mib"] is None,
                "Authority or unmeasured resource claim refused")
        require(isinstance(row["limitations"], str) and 0 < len(row["limitations"].strip()) <= 500,
                "Explicit limitation required")
        proof = row["evidence"]
        require(isinstance(proof, dict) and set(proof) == {"path", "start", "end"}
                and isinstance(proof["path"], str) and len(proof["path"]) <= 300
                and PATH.fullmatch(proof["path"]) and all(p not in (".", "..") for p in proof["path"].split("/"))
                and type(proof["start"]) is int and type(proof["end"]) is int
                and 1 <= proof["start"] <= proof["end"] <= 1000000,
                "Malformed source reference")
    return declarations


def discover(declarations, catalog, capability, input_contract, output_contract, mode):
    """Exact-label discovery, not structural compatibility or admission."""
    validate(declarations, catalog)
    require(all(is_token(v) for v in (capability, input_contract, output_contract))
            and mode in ("synthetic", "opt-in-local"), "Invalid discovery request")
    matches = sorted((r["id"] for r in declarations["entries"]
                      if (r["capability"], r["input_contract"], r["output_contract"], r["mode"])
                      == (capability, input_contract, output_contract, mode)))
    return {"schema": SCHEMA, "authority": "NONE",
            "decision": "REVIEW_CANDIDATES" if matches else "NO_DECLARED_MATCH",
            "matches": matches, "execution_authorized": False,
            "limitations": "Exact catalog labels only; source claims, current visibility, interface compatibility and authorization require independent review."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability")
    parser.add_argument("--input-contract")
    parser.add_argument("--output-contract")
    parser.add_argument("--mode", choices=("synthetic", "opt-in-local"))
    args = parser.parse_args(argv)
    try:
        declarations, catalog = read_json(DECLARATIONS), read_json(CATALOG)
        query = (args.capability, args.input_contract, args.output_contract, args.mode)
        if any(v is not None for v in query):
            require(all(v is not None for v in query), "Complete query required")
            result = discover(declarations, catalog, *query)
        else:
            validate(declarations, catalog)
            result = {"schema": SCHEMA, "authority": "NONE",
                      "declaration_count": len(declarations["entries"]), "execution_authorized": False}
    except (ValueError, OSError, RecursionError):
        parser.exit(2, "Capability discovery refused invalid local input.\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
