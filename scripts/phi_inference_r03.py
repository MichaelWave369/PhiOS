"""R03: opt-in synthetic local Ollama benchmark; not a routing authority."""
import argparse
import http.client
import json
import re
import sys
import time

SUITE = "phi-inference-smoke-v1"
MAX_RESPONSE = 1024 * 1024
CASES = (
    ("arithmetic", "Return only the integer result of 17 * 6 - 11.", "91"),
    ("ordering", "Sort these words alphabetically: pear, apple, lime. Return only comma-separated words with no spaces.", "apple,lime,pear"),
    ("logic", "Every dax is a mip. No mip is a zol. Can a dax be a zol? Return only yes or no in lowercase.", "no"),
    ("extraction", "Record: id=R42; owner=Sam; priority=low. Return only the id value.", "R42"),
    ("code_trace", "Python: x = [2, 5, 8]; print(sum(x[1:])). Return only the printed integer.", "13"),
    ("instruction", "Return exactly the following identifier, including case and hyphen: PHI-369", "PHI-369"),
)


def validate_model(model):
    # Require explicit tags, no whitespace or URL-like names.
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", model))


def metrics(data):
    result = {}
    for key in ("total_duration", "load_duration", "prompt_eval_count",
                "prompt_eval_duration", "eval_count", "eval_duration"):
        value = data.get(key)
        if type(value) is int and 0 <= value <= 10**15:
            result[key] = value
    count, duration = result.get("eval_count"), result.get("eval_duration")
    if count is not None and duration:
        result["generation_tokens_per_second"] = round(count * 1e9 / duration, 3)
    return result


def attempt(model, case, timeout=120):
    name, prompt, expected = case
    start = time.monotonic()
    row = {"case": name, "status": "ERROR", "correct": False}
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                           "options": {"temperature": 0, "seed": 369, "num_predict": 128}})
        conn.request("POST", "/api/generate", body=body,
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            row.update(reason="HTTP_STATUS", http_status=response.status)
        else:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                row["reason"] = "RESPONSE_LIMIT"
            else:
                data = json.loads(raw)
                if (not isinstance(data, dict) or data.get("done") is not True
                        or data.get("error") or data.get("model") != model
                        or not isinstance(data.get("response"), str)):
                    row["reason"] = "INVALID_RESPONSE"
                else:
                    correct = data["response"].strip() == expected
                    row.update(status="CORRECT" if correct else "INCORRECT",
                               correct=correct, ollama_metrics=metrics(data))
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        row["reason"] = "TRANSPORT_OR_PARSE"
    finally:
        conn.close()
    row["wall_seconds"] = round(time.monotonic() - start, 6)
    return row


def benchmark(models, repeats, timeout):
    if (not 1 <= len(models) <= 3 or len(set(models)) != len(models)
            or not all(validate_model(m) for m in models)
            or not 1 <= repeats <= 3 or not 1 <= timeout <= 300):
        raise ValueError("invalid benchmark bounds")
    reports = []
    # Rotate model order each round. Calls remain sequential.
    for model in models:
        reports.append({"model": model, "attempts": []})
    for run in range(repeats):
        offset = run % len(models)
        for index in list(range(offset, len(models))) + list(range(offset)):
            report = reports[index]
            for case in CASES:
                row = attempt(report["model"], case, timeout)
                row["repeat"] = run + 1
                report["attempts"].append(row)
                # Stop the complete run on a transport/protocol error rather than
                # hammering a failed local daemon. Retain partial evidence.
                if row["status"] == "ERROR":
                    return summarize(reports, repeats, complete=False)
    return summarize(reports, repeats, complete=True)


def summarize(reports, repeats, complete):
    for report in reports:
        rows = report["attempts"]
        successes = [r for r in rows if r["status"] != "ERROR"]
        correct = sum(r["correct"] for r in rows)
        report.update(attempted=len(rows), correct=correct,
                      errors=sum(r["status"] == "ERROR" for r in rows),
                      expected_attempts=len(CASES) * repeats,
                      exact_match_fraction=(correct / len(rows) if rows else None),
                      median_wall_seconds=median([r["wall_seconds"] for r in successes]))
    return {"schema": 1, "suite": SUITE, "repeats": repeats,
            "complete": complete, "operator_declared_offline": True,
            "offline_verified": False, "routing_authority": False,
            "reports": reports}


def median(values):
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return round((values[middle - 1] + values[middle]) / 2, 6)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True,
                        help="Exact installed non-cloud model tag; up to three")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--confirm-offline", action="store_true",
                        help="Confirm external network blocked and tags are local")
    args = parser.parse_args(argv)
    if not args.confirm_offline:
        parser.error("explicit offline confirmation required")
    try:
        report = benchmark(args.model, args.repeats, args.timeout)
    except ValueError:
        parser.error("use 1-3 distinct exact model tags, 1-3 repeats and 1-300 second timeout")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
