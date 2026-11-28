import json

import pytest

from phios import local_chat_smoke as li


MODEL = "qwen3:4b"


def answer(content, **overrides):
    return {
        "model": MODEL, "done": True, "done_reason": "stop",
        "message": {"role": "assistant", "content": content},
        "eval_count": 10, "eval_duration": 500_000_000,
        **overrides,
    }


def backend(monkeypatch, replies, tags=None):
    calls = []
    replies = iter(replies)

    def request(method, path, timeout, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {"models": [{"name": MODEL}]} if tags is None else tags
        return next(replies)

    monkeypatch.setattr(li, "request_json", request)
    return calls


def test_two_turn_context_and_metrics(monkeypatch):
    calls = backend(monkeypatch, [answer("READY"), answer(li.TOKEN)])
    report = li.smoke(MODEL)
    assert report["status"] == "LOOPBACK_CHAT_MATCH_REVIEW_ONLY"
    assert len(calls) == 3
    assert calls[1][2]["messages"] == [{"role": "user", "content": li.FIRST}]
    assert calls[2][2]["messages"] == [
        {"role": "user", "content": li.FIRST},
        {"role": "assistant", "content": "READY"},
        {"role": "user", "content": li.SECOND},
    ]
    for _, _, payload in calls[1:]:
        assert payload["stream"] is False
        assert payload["options"]["num_predict"] == 96
        assert "tools" not in payload
    assert report["turns"][0]["backend_tokens_per_second"] == 20
    assert not report["offline_execution_verified"]
    assert not report["gpu_execution_verified"]
    assert not report["companion_integration_verified"]
    assert not report["authority_granted"]
    assert report["backend_claims_unverified"]
    assert li.TOKEN not in json.dumps(report)


def test_unexpected_first_output_not_replayed(monkeypatch):
    calls = backend(monkeypatch, [answer("PRIVATE unexpected output")])
    report = li.smoke(MODEL)
    assert report["status"] == "RESPONSE_MISMATCH"
    assert len(calls) == 2
    assert "PRIVATE" not in json.dumps(report)


def test_second_mismatch(monkeypatch):
    backend(monkeypatch, [answer("READY"), answer("wrong")])
    assert li.smoke(MODEL)["status"] == "RESPONSE_MISMATCH"


@pytest.mark.parametrize("tags", [
    {"models": []},
    {"models": [{"name": MODEL, "remote_host": "example.invalid"}]},
    {"models": [{"name": MODEL, "remote_model": "other"}]},
    {"models": [{"name": MODEL}, {"name": MODEL}]},
    {"models": [{"name": MODEL, "model": "different"}]},
    {"models": [None]},
])
def test_bad_inventory_blocks_chat(monkeypatch, tags):
    calls = backend(monkeypatch, [], tags)
    with pytest.raises(ValueError):
        li.smoke(MODEL)
    assert len(calls) == 1


@pytest.mark.parametrize("model", ["foo-cloud", "foo:cloud", "../model", "", "model name"])
def test_bad_model_no_network(monkeypatch, model):
    calls = backend(monkeypatch, [])
    with pytest.raises(ValueError):
        li.smoke(model)
    assert not calls


@pytest.mark.parametrize("reply", [
    answer("READY", done=False),
    answer("READY", done_reason="length"),
    answer("READY", model="other"),
    answer("READY", remote_host="example.invalid"),
    answer("READY", message={"role": "assistant", "content": "READY", "tool_calls": [{}]}),
    answer("READY", message={"role": "user", "content": "READY"}),
    answer(""),
])
def test_incomplete_or_unexpected_answer(monkeypatch, reply):
    calls = backend(monkeypatch, [reply])
    with pytest.raises(ValueError):
        li.smoke(MODEL)
    assert len(calls) == 2


@pytest.mark.parametrize(("status", "body"), [
    (302, b""), (500, b""), (200, b"bad-json"),
    (200, b"x" * (li.MAX_BODY + 1)), (200, b'{"error":"private"}'),
])
def test_http_rejects_bad_responses(monkeypatch, status, body):
    calls = []

    class Fake:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 11434, 5)

        def request(self, method, path, body, headers):
            calls.append((method, path))
            assert body is None

        def getresponse(self):
            return self

        def read(self, length):
            assert length == li.MAX_BODY + 1
            return body[:length]

        def close(self):
            calls.append("closed")

    Fake.status = status
    monkeypatch.setattr(li.http.client, "HTTPConnection", Fake)
    with pytest.raises(ValueError):
        li.request_json("GET", "/api/tags", 5)
    assert calls == [("GET", "/api/tags"), "closed"]


def test_default_cli_no_network(monkeypatch, capsys):
    calls = backend(monkeypatch, [])
    monkeypatch.setattr("sys.argv", ["smoke", "--model", MODEL])
    assert li.main() == 2
    assert not calls
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_RUN_EXPLICIT_OPT_IN_REQUIRED"


def test_metrics_reject_invalid_counters():
    assert li.metrics({"eval_count": True, "eval_duration": -1}) == {}
