import hashlib
import json

import pytest

from phios import local_companion_review as review


def fixture(depth="quick"):
    rows = []
    for i, (key, prompt, ref) in enumerate(review.CASES):
        rows.append({
            "case_id": key, "prompt": prompt, "reference": ref,
            "order": "solo_first" if i % 2 == 0 else "council_first",
            "council_depth": depth,
            "solo": {"answer": ref or "Use the SQLite backup API.", "elapsed_ms": 10, "model_requests": 1},
            "council": {"answer": ref or "Review the copied database.", "elapsed_ms": 40,
                        "model_requests": 4 if depth == "quick" else 7},
        })
    return rows


def encode(rows):
    return ("\n".join(json.dumps({"format_version": 1, "model": "qwen3:4b", "evaluation": row}) for row in rows) + "\n").encode()


@pytest.mark.parametrize("depth,count", [("quick", 12), ("debate", 21)])
def test_native_shape(depth, count):
    raw = encode(fixture(depth))
    result = review.review(raw, depth, "qwen3:4b")
    assert result["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["solo_declared_requests"] == 3
    assert result["council_declared_requests"] == count
    assert result["cases"][0]["solo"]["exact_match"] is True
    assert result["cases"][2]["council"]["exact_match"] is None
    assert result["native_execution_verified"] is False
    assert result["superiority_verified"] is False
    assert "Use the SQLite backup API." not in json.dumps(result)


@pytest.mark.parametrize("field,value", [
    ("case_id", "other"), ("prompt", "different"), ("reference", "fake"),
    ("order", "council_first"), ("council_depth", "debate"),
])
def test_reject_changed_case(field, value):
    rows = fixture()
    rows[0][field] = value
    with pytest.raises(ValueError):
        review.review(encode(rows), "quick", "qwen3:4b")


@pytest.mark.parametrize("field,value", [
    ("elapsed_ms", True), ("elapsed_ms", -1), ("model_requests", 2), ("answer", ""),
])
def test_reject_invalid_answer(field, value):
    rows = fixture()
    rows[0]["solo"][field] = value
    with pytest.raises(ValueError):
        review.review(encode(rows), "quick", "qwen3:4b")


def test_wrong_answer_is_not_transport_failure():
    rows = fixture()
    rows[0]["solo"]["answer"] = "wrong"
    assert review.review(encode(rows), "quick", "qwen3:4b")["cases"][0]["solo"]["exact_match"] is False


@pytest.mark.parametrize("raw", [b"", b"not json", b"\xff", b"x" * (review.MAX_REPORT + 1)])
def test_bad_bytes(raw):
    with pytest.raises(ValueError):
        review.review(raw, "quick", "qwen3:4b")


def test_partial_and_reordered():
    rows = fixture()
    for selection in (rows[:2], rows[::-1], rows + rows[:1]):
        with pytest.raises(ValueError):
            review.review(encode(selection), "quick", "qwen3:4b")


def test_suite_matches_cases():
    assert review.suite()["cases"][0]["id"] == "literal"
    assert len(review.suite()["cases"]) == 3


def test_native_model_and_envelope():
    raw = encode(fixture())
    with pytest.raises(ValueError):
        review.review(raw, "quick", "other:latest")
    with pytest.raises(ValueError):
        review.review(raw.replace(b'"format_version": 1', b'"format_version": true'), "quick", "qwen3:4b")
    with pytest.raises(ValueError):
        review.review(raw.replace(b'"evaluation":', b'"different":'), "quick", "qwen3:4b")
