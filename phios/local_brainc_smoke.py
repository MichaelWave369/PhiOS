"""Opt-in native BrainC chat pilot for a disposable, empty loopback instance."""

import argparse
import getpass
import http.client
import json
import re
import time
import uuid

from phios.local_chat_smoke import FIRST, SECOND, TOKEN, valid_model

HOST = "127.0.0.1"
PORT = 8369
MAX_BODY = 1024 * 1024


def request(method, path, token=None, payload=None, timeout=60):
    """Use the dedicated pilot port only; no redirects, proxies or fallback."""
    allowed = {("GET", "/health/ready"), ("GET", "/preferences"), ("POST", "/chat")}
    history = method == "GET" and re.fullmatch(
        r"/history\?conversation_id=pilot-[0-9a-f]{32}", path
    )
    if (method, path) not in allowed and not history:
        raise ValueError("unsupported pilot route")
    headers = {"Accept": "text/plain" if method == "POST" else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("unexpected HTTP status")
        if response.getheader("X-Tool-Used") is not None or response.getheader("X-Tool-Result") is not None:
            raise ValueError("unexpected tool activity")
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError("response exceeds limit")
        if method == "POST":
            if content_type != "text/plain":
                raise ValueError("unexpected chat content type")
            answer = data.decode("utf-8").strip()
            if not answer or len(answer) > 512 or "[ERROR]" in answer:
                raise ValueError("incomplete or unexpected chat response")
            return answer
        if content_type != "application/json":
            raise ValueError("unexpected JSON content type")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("invalid JSON response")
        return value
    finally:
        conn.close()


def check_ready(value, model, message_count):
    checks = value.get("checks")
    if not isinstance(checks, dict) or value.get("status") != "ok":
        raise ValueError("BrainC readiness not established")
    db, ollama = checks.get("database"), checks.get("ollama")
    if (not isinstance(db, dict) or db.get("status") != "ok"
            or type(db.get("message_count")) is not int
            or db["message_count"] != message_count
            or not isinstance(ollama, dict) or ollama.get("status") != "ok"
            or ollama.get("configured_model_registered") is not True
            or not isinstance(ollama.get("models"), list)
            or ollama["models"].count(model) != 1
            or "phiserve" in checks or "local_inference" in checks):
        raise ValueError("unexpected database or runtime state")


def check_history(value, session, expected):
    if value.get("conversation_id") != session or not isinstance(value.get("messages"), list):
        raise ValueError("unexpected conversation history")
    rows = value["messages"]
    if len(rows) != len(expected):
        raise ValueError("unexpected history length")
    for row, (role, content) in zip(rows, expected):
        if (not isinstance(row, dict) or row.get("conversation_id") != session
                or row.get("role") != role or not isinstance(row.get("message"), str)
                or row["message"].strip() != content):
            raise ValueError("unexpected persisted conversation")


def smoke(model, token, timeout=60):
    if (not valid_model(model) or "cloud" in model.lower()
            or not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{20,4096}", token)
            or type(timeout) is not int or not 1 <= timeout <= 120):
        raise ValueError("invalid pilot configuration")
    session = "pilot-" + uuid.uuid4().hex
    history_path = "/history?conversation_id=" + session
    check_ready(request("GET", "/health/ready", timeout=timeout), model, 0)
    prefs = request("GET", "/preferences", token, timeout=timeout)
    if prefs.get("model") != model or prefs.get("system_prompt_override"):
        raise ValueError("unexpected model preference or custom override")
    check_history(request("GET", history_path, token, timeout=timeout), session, [])
    turns = []
    expected = []
    for prompt, target in ((FIRST, "READY"), (SECOND, TOKEN)):
        started = time.monotonic()
        answer = request("POST", "/chat", token, {
            "message": prompt, "conversation_id": session, "tools_enabled": False,
        }, timeout)
        elapsed = round(time.monotonic() - started, 3)
        expected.extend([("user", prompt), ("assistant", answer)])
        check_history(request("GET", history_path, token, timeout=timeout), session, expected)
        turns.append({"exact_match": answer == target, "wall_seconds": elapsed,
                      "persisted_history_matches": True})
        if answer != target:
            break
    check_ready(request("GET", "/health/ready", timeout=timeout), model, len(expected))
    passed = len(turns) == 2 and all(row["exact_match"] for row in turns)
    return {
        "schema": "phios.local-intelligence.brainc-smoke.r03c",
        "status": "NATIVE_CHAT_MATCH_REVIEW_ONLY" if passed else "RESPONSE_MISMATCH",
        "turns": turns,
        "reported_empty_database_preflight": True,
        "tools_disabled_in_requests": True,
        "backend_identity_verified": False,
        "offline_execution_verified": False,
        "disposable_isolation_verified": False,
        "gpu_execution_verified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--confirm-disposable-offline", action="store_true")
    args = parser.parse_args()
    if not (args.run_live and args.confirm_disposable_offline):
        print(json.dumps({"status": "NOT_RUN_EXPLICIT_OPT_IN_REQUIRED"}))
        return 2
    try:
        token = getpass.getpass("Disposable BrainC access token: ")
        report = smoke(args.model, token, args.timeout)
    except (OSError, ValueError, http.client.HTTPException, EOFError, RecursionError):
        print(json.dumps({"status": "PILOT_OR_RESPONSE_UNQUALIFIED"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "NATIVE_CHAT_MATCH_REVIEW_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
