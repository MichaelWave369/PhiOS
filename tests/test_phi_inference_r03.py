import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location(
    "phi_inference_r03", Path(__file__).resolve().parents[1] / "scripts" / "phi_inference_r03.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_requires_confirmation():
    with patch.object(mod, "attempt") as call:
        with pytest.raises(SystemExit) as e:
            mod.main(["--model", "test:local"])
        assert e.value.code == 2
        call.assert_not_called()


@pytest.mark.parametrize("models,repeats,timeout", [
    (["bad"], 1, 1), (["a:1", "a:1"], 1, 1), (["a:1"], 4, 1),
    (["a:1"], 1, 301), (["https://bad:1"], 1, 1), ([], 1, 1),
])
def test_invalid_bounds(models, repeats, timeout):
    with patch.object(mod, "attempt") as call:
        with pytest.raises(ValueError):
            mod.benchmark(models, repeats, timeout)
        call.assert_not_called()


@pytest.mark.parametrize("status,data,expected", [
    (200, {"done": True, "model": "test:local", "response": " 91 "}, "CORRECT"),
    (200, {"done": True, "model": "test:local", "response": "92"}, "INCORRECT"),
    (200, {"done": False, "model": "test:local", "response": "91"}, "ERROR"),
    (200, {"done": True, "model": "wrong:local", "response": "91"}, "ERROR"),
    (200, {"done": True, "model": "test:local", "response": 91}, "ERROR"),
    (302, {}, "ERROR"),
    (500, {}, "ERROR"),
])
def test_attempt(status, data, expected):
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        conn = factory.return_value
        response = conn.getresponse.return_value
        response.status = status
        response.read.return_value = json.dumps(data).encode()
        row = mod.attempt("test:local", mod.CASES[0], 15)
        assert row["status"] == expected
        assert row["correct"] == (expected == "CORRECT")
        assert row["wall_seconds"] >= 0
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=15)
        assert conn.request.call_args.args[:2] == ("POST", "/api/generate")
        assert "91" not in json.loads(conn.request.call_args.kwargs["body"])["prompt"]
        conn.close.assert_called_once()


def test_transport_and_size():
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        factory.return_value.request.side_effect = TimeoutError
        assert mod.attempt("test:local", mod.CASES[0])["reason"] == "TRANSPORT_OR_PARSE"
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        response = factory.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b"x" * (mod.MAX_RESPONSE + 1)
        assert mod.attempt("test:local", mod.CASES[0])["reason"] == "RESPONSE_LIMIT"


def test_metrics_are_bounded():
    assert mod.metrics({"eval_count": 12, "eval_duration": 2_000_000_000,
                        "prompt_eval_count": True, "load_duration": -1}) == {
        "eval_count": 12, "eval_duration": 2_000_000_000,
        "generation_tokens_per_second": 6.0}
    assert "generation_tokens_per_second" not in mod.metrics({"eval_count": 1, "eval_duration": 0})


def test_rotated_sequential_order_and_correctness():
    with patch.object(mod, "attempt", return_value=None) as call:
        def fake(model, case, timeout):
            correct = case[0] != "logic"
            return {"case": case[0], "correct": correct,
                    "status": "CORRECT" if correct else "INCORRECT", "wall_seconds": 1}
        call.side_effect = fake
        report = mod.benchmark(["a:1", "b:1"], 2, 1)
        assert [c.args[0] for c in call.call_args_list[::6]] == ["a:1", "b:1", "b:1", "a:1"]
    assert report["complete"] and not report["offline_verified"] and not report["routing_authority"]
    assert all(r["correct"] == 10 and r["attempted"] == 12 for r in report["reports"])


def test_error_stops_and_preserves_partial_report():
    with patch.object(mod, "attempt", side_effect=[
        {"case": "arithmetic", "correct": True, "status": "CORRECT", "wall_seconds": 1},
        {"case": "ordering", "correct": False, "status": "ERROR", "wall_seconds": 2},
    ]) as call:
        report = mod.benchmark(["a:1", "b:1"], 1, 1)
    assert call.call_count == 2 and not report["complete"]
    assert report["reports"][0]["correct"] == 1
    assert report["reports"][0]["errors"] == 1
    assert report["reports"][1]["exact_match_fraction"] is None


def test_cli_complete_does_not_mean_quality_pass(capsys):
    with patch.object(mod, "attempt", side_effect=lambda model, case, timeout: {
        "case": case[0], "correct": False, "status": "INCORRECT", "wall_seconds": 1}):
        assert mod.main(["--model", "a:1", "--confirm-offline"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["reports"][0]["correct"] == 0
