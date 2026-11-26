"""Read-only workstation readiness and optional loopback inference smoke."""
import argparse
import http.client
import json
import platform
import shutil
import sys

TOOLS = ("git", "ollama", "cargo", "node", "nvidia-smi")
MARKER = "PHI_LOCAL_OK"
MAX_RESPONSE = 1024 * 1024


def inventory():
    return {
        "schema": 1,
        "platform": platform.system(),
        "python": platform.python_version(),
        "tools_on_path": {name: shutil.which(name) is not None for name in TOOLS},
        "inference": {"status": "NOT_RUN"},
        "offline_verified": False,
        "certification": "UNVERIFIED",
    }


def smoke(model, timeout=120):
    # Direct IPv4 loopback, no proxy, redirects, retries, or model downloads.
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        payload = json.dumps({
            "model": model, "prompt": "Reply with exactly PHI_LOCAL_OK and nothing else.",
            "stream": False, "options": {"temperature": 0, "num_predict": 64},
        })
        conn.request("POST", "/api/generate", body=payload,
                     headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        if res.status != 200:
            return {"status": "FAIL", "reason": "HTTP_STATUS", "http_status": res.status}
        raw = res.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return {"status": "FAIL", "reason": "RESPONSE_LIMIT"}
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("done") is not True or data.get("error"):
            return {"status": "FAIL", "reason": "INCOMPLETE_OR_ERROR"}
        if data.get("model") != model:
            return {"status": "FAIL", "reason": "MODEL_MISMATCH"}
        if not isinstance(data.get("response"), str) or data["response"].strip() != MARKER:
            return {"status": "FAIL", "reason": "MARKER_MISMATCH"}
        return {"status": "PASS", "scope": "loopback_marker_only"}
    except (OSError, ValueError, http.client.HTTPException):
        return {"status": "FAIL", "reason": "TRANSPORT_OR_PARSE"}
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Exact installed Ollama model tag")
    parser.add_argument("--confirm-offline", action="store_true",
                        help="Operator confirms external network is blocked; not independently verified")
    args = parser.parse_args(argv)
    if args.model and (not args.confirm_offline or ":" not in args.model or
                       len(args.model) > 200 or any(c.isspace() for c in args.model)):
        parser.error("inference requires an exact model tag and --confirm-offline")
    if args.confirm_offline and not args.model:
        parser.error("--confirm-offline requires --model")
    report = inventory()
    if args.model:
        report["operator_declared_offline"] = True
        report["inference"] = smoke(args.model)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["inference"]["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
