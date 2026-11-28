"""Opt-in loopback Ollama two-turn chat smoke; no tools or private prompts."""

import argparse
import http.client
import json
import re
import time

HOST = "127.0.0.1"
PORT = 11434
MAX_BODY = 2 * 1024 * 1024
TOKEN = "PHI369-COPPER-ORBIT"
FIRST = f"Remember this public test code: {TOKEN}. Reply with only READY."
SECOND = "What was the test code? Reply with only the code."
MODEL_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?"


def cloud_hint(row):
    name = row.get("name", row.get("model", ""))
    return bool(
        row.get("remote_host") or row.get("remote_model")
        or (isinstance(name, str) and (
            name.casefold().endswith("-cloud") or name.casefold().endswith(":cloud")
        ))
    )


def valid_model(model):
    return (
        isinstance(model, str) and 1 <= len(model) <= 128
        and re.fullmatch(MODEL_PATTERN, model) is not None
        and all(part not in ("", ".", "..") for part in model.split("/"))
        and not cloud_hint({"name": model})
    )


def request_json(method, path, timeout, payload=None):
    """Fixed loopback routes only, no redirects or proxies; bounded response."""
    if (method, path) not in (("GET", "/api/tags"), ("POST", "/api/chat")):
        raise ValueError("unsupported request")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers={
            "Accept": "application/json", "Content-Type": "application/json",
        })
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("backend did not return HTTP 200")
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError("response exceeds size limit")
        result = json.loads(data)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("invalid backend response")
        return result
    finally:
        conn.close()


def select_model(tags, model):
    rows = tags.get("models")
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ValueError("invalid model inventory")
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid model entry")
        if row.get("name") == model or row.get("model") == model:
            if any(row.get(key) not in (None, model) for key in ("name", "model")):
                raise ValueError("inconsistent model identity")
            matches.append(row)
    if len(matches) != 1 or cloud_hint(matches[0]):
        raise ValueError("exact non-cloud-hinted model required")


def metrics(result):
    """Report only backend-declared nonnegative integer counters."""
    counters = {}
    for key in ("prompt_eval_count", "eval_count", "eval_duration", "load_duration"):
        value = result.get(key)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            counters[key] = value
    count = counters.get("eval_count")
    duration = counters.get("eval_duration")
    if count is not None and duration:
        counters["backend_tokens_per_second"] = round(count * 1e9 / duration, 3)
    return counters


def turn(model, messages, timeout):
    started = time.monotonic()
    result = request_json("POST", "/api/chat", timeout, {
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0, "num_predict": 96, "num_ctx": 2048},
    })
    elapsed = round(time.monotonic() - started, 3)
    message = result.get("message")
    if (result.get("model") != model or result.get("done") is not True
            or result.get("done_reason") != "stop" or cloud_hint(result)
            or not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or not isinstance(message.get("content"), str)
            or not 0 < len(message["content"].strip()) <= 512):
        raise ValueError("incomplete or unexpected chat response")
    content = message["content"].strip()
    return content, {"wall_seconds": elapsed, **metrics(result)}


def smoke(model, timeout=60):
    if not valid_model(model) or type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("invalid model or timeout")
    select_model(request_json("GET", "/api/tags", timeout), model)
    messages = [{"role": "user", "content": FIRST}]
    first, first_metrics = turn(model, messages, timeout)
    first_ok = first == "READY"
    # Only the expected public acknowledgment may enter the second request.
    # Unexpected generated output is neither replayed nor stored.
    turns = [{"exact_match": first_ok, **first_metrics}]
    if first_ok:
        messages = [
            *messages, {"role": "assistant", "content": "READY"},
            {"role": "user", "content": SECOND},
        ]
        second, second_metrics = turn(model, messages, timeout)
        turns.append({"exact_match": second == TOKEN, **second_metrics})
    passed = len(turns) == 2 and all(row["exact_match"] for row in turns)
    return {
        "schema": "phios.local-intelligence.chat-smoke.r03",
        "status": "LOOPBACK_CHAT_MATCH_REVIEW_ONLY" if passed else "RESPONSE_MISMATCH",
        "turns": turns,
        "backend_claims_unverified": True,
        "offline_execution_verified": False,
        "gpu_execution_verified": False,
        "companion_integration_verified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="exact installed Ollama tag")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--run-live", action="store_true")
    args = parser.parse_args()
    if not args.run_live:
        print(json.dumps({"status": "NOT_RUN_EXPLICIT_OPT_IN_REQUIRED"}))
        return 2
    try:
        report = smoke(args.model, args.timeout)
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        print(json.dumps({"status": "BACKEND_OR_RESPONSE_UNQUALIFIED"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "LOOPBACK_CHAT_MATCH_REVIEW_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
