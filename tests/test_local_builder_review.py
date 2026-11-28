import hashlib
import json

import pytest

from phios import local_builder_review as lab


def candidate(**overrides):
    expressions = {
        "port_bounds": "1 <= port <= 65535",
        "byte_budget": "used >= 0 and requested >= 0 and limit >= 0 and used + requested <= limit",
        "retry_limit": "attempts >= 0 and limit >= 0 and attempts < limit",
    }
    expressions.update(overrides)
    return {
        "schema": "phios.local-builder.candidate.r04",
        "repairs": [{"id": key, "expression": value} for key, value in expressions.items()],
    }


def encode(value):
    return json.dumps(value).encode("utf-8")


def test_correct_repairs():
    raw = encode(candidate())
    receipt = lab.review(raw)
    assert receipt["status"] == "FIXTURE_MATCH_REVIEW_ONLY"
    assert receipt["candidate_sha256"] == hashlib.sha256(raw).hexdigest()
    assert [row["total"] for row in receipt["tasks"]] == [11, 216, 36]
    assert all(row["passed"] == row["total"] for row in receipt["tasks"])
    for key in ("general_correctness_verified", "model_origin_verified",
                "candidate_code_executed", "repository_modified", "authority_granted"):
        assert receipt[key] is False
    assert "1 <= port" not in json.dumps(receipt)


def test_original_bugs_fail():
    raw = encode(candidate(**{task["id"]: task["buggy"] for task in lab.TASKS}))
    receipt = lab.review(raw)
    assert receipt["status"] == "FIXTURE_MISMATCH"
    assert all(row["passed"] < row["total"] for row in receipt["tasks"])


@pytest.mark.parametrize("expression", [
    "__import__('os')", "port.real", "port[0]", "lambda: port",
    "port ** 2", "[port]", "port in [1]", "True", "port",
    "other > 0", "port > 9999999999999999999", "port > 0.0",
    "port > 0 and 1", "port > 0\nprint(port)", "(port := 1)",
    "not port", "port > 0 or __import__('os')", "x" * 257,
])
def test_unsupported_grammar(expression):
    with pytest.raises(ValueError):
        lab.review(encode(candidate(port_bounds=expression)))


def test_missing_duplicate_and_extra_entries():
    for mutation in ("missing", "duplicate", "extra"):
        value = candidate()
        if mutation == "missing":
            value["repairs"].pop()
        elif mutation == "duplicate":
            value["repairs"][0] = value["repairs"][1]
        else:
            value["repairs"][0]["extra"] = True
        with pytest.raises(ValueError):
            lab.review(encode(value))


@pytest.mark.parametrize("raw", [
    b"", b"not json", b"\xff", b"x" * (lab.MAX_INPUT + 1),
    b'{"schema":"a","schema":"b","repairs":[]}',
])
def test_invalid_candidate(raw):
    with pytest.raises(ValueError):
        lab.review(raw)


def test_suite_does_not_include_fixture_domain_or_expected_answers():
    value = lab.suite()
    assert len(value["tasks"]) == 3
    assert all("domain" not in task for task in value["tasks"])
    assert value["tasks"][0]["buggy"] == "0 <= port < 65535"


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    path = tmp_path / "candidate.json"
    monkeypatch.setattr("sys.argv", ["review", "review", "--candidate", str(path)])
    for raw, status, exit_code in (
        (encode(candidate()), "FIXTURE_MATCH_REVIEW_ONLY", 0),
        (encode(candidate(port_bounds="port > 0")), "FIXTURE_MISMATCH", 3),
        (b"bad", "INVALID_CANDIDATE", 2),
    ):
        path.write_bytes(raw)
        assert lab.main() == exit_code
        assert json.loads(capsys.readouterr().out)["status"] == status
