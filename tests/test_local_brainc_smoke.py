import json

import pytest

from phios import local_brainc_smoke as pilot


MODEL = "qwen3:4b"
ACCESS = "test-access-token-not-real-123"


def fake_backend(monkeypatch, *, initial_count=0, preference=MODEL,
                 answers=("READY", pilot.TOKEN), bad_history=False):
    calls = []
    messages = []
    replies = iter(answers)

    def request(method, path, token=None, payload=None, timeout=60):
        calls.append((method, path, token, payload))
        if path == "/health/ready":
            return {"status": "ok", "checks": {
                "database": {"status": "ok", "message_count": initial_count + len(messages)},
                "ollama": {"status": "ok", "models": [MODEL], "configured_model_registered": True},
            }}
        assert token == ACCESS
        if path == "/preferences":
            return {"model": preference, "system_prompt_override": None}
        if path == "/chat":
            assert payload["tools_enabled"] is False
            assert payload["conversation_id"].startswith("pilot-")
            reply = next(replies)
            for role, content in (("user", payload["message"]), ("assistant", reply)):
                messages.append({"role": role, "message": content,
                                 "conversation_id": payload["conversation_id"]})
            return reply
        assert path.startswith("/history?conversation_id=pilot-")
        return {"conversation_id": path.split("=", 1)[1],
                "messages": [] if bad_history else list(messages)}

    monkeypatch.setattr(pilot, "request", request)
    return calls


def test_native_two_turn_and_persistence(monkeypatch):
    calls = fake_backend(monkeypatch)
    report = pilot.smoke(MODEL, ACCESS)
    assert report["status"] == "NATIVE_CHAT_MATCH_REVIEW_ONLY"
    posts = [row[3] for row in calls if row[0] == "POST"]
    assert [row["message"] for row in posts] == [pilot.FIRST, pilot.SECOND]
    assert posts[0]["conversation_id"] == posts[1]["conversation_id"]
    assert all(row["persisted_history_matches"] for row in report["turns"])
    assert not report["offline_execution_verified"]
    assert not report["disposable_isolation_verified"]
    assert not report["authority_granted"]
    serialized = json.dumps(report)
    assert ACCESS not in serialized and pilot.TOKEN not in serialized
    assert posts[0]["conversation_id"] not in serialized


@pytest.mark.parametrize("kwargs", [{"initial_count": 1}, {"preference": "wrong:latest"}])
def test_preflight_blocks_writes(monkeypatch, kwargs):
    calls = fake_backend(monkeypatch, **kwargs)
    with pytest.raises(ValueError):
        pilot.smoke(MODEL, ACCESS)
    assert not any(row[0] == "POST" for row in calls)


def test_wrong_answer_stops_after_first_turn(monkeypatch):
    calls = fake_backend(monkeypatch, answers=("wrong",))
    assert pilot.smoke(MODEL, ACCESS)["status"] == "RESPONSE_MISMATCH"
    assert sum(row[0] == "POST" for row in calls) == 1


def test_missing_persistence_blocks_next_turn(monkeypatch):
    calls = fake_backend(monkeypatch, bad_history=True)
    with pytest.raises(ValueError):
        pilot.smoke(MODEL, ACCESS)
    assert sum(row[0] == "POST" for row in calls) == 1


@pytest.mark.parametrize("model,token", [
    ("cloud-model:latest", ACCESS), ("../bad", ACCESS), (MODEL, "short"),
    (MODEL, ACCESS + "\n"),
])
def test_bad_inputs_no_calls(monkeypatch, model, token):
    calls = fake_backend(monkeypatch)
    with pytest.raises(ValueError):
        pilot.smoke(model, token)
    assert calls == []


@pytest.mark.parametrize("flags", [[], ["--run-live"], ["--confirm-disposable-offline"]])
def test_cli_requires_both_flags(monkeypatch, capsys, flags):
    calls = fake_backend(monkeypatch)
    monkeypatch.setattr("sys.argv", ["smoke", "--model", MODEL, *flags])
    monkeypatch.setattr(pilot.getpass, "getpass", lambda _: pytest.fail("unexpected credential prompt"))
    assert pilot.main() == 2
    assert calls == []
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_RUN_EXPLICIT_OPT_IN_REQUIRED"


@pytest.mark.parametrize("status,headers,body", [
    (302, {}, b""), (200, {"X-Tool-Used": "search"}, b"READY"),
    (200, {"Content-Type": "application/json"}, b"READY"),
    (200, {"Content-Type": "text/plain"}, b"[ERROR] unavailable"),
    (200, {"Content-Type": "text/plain"}, b"x" * (pilot.MAX_BODY + 1)),
])
def test_http_rejects_unqualified_chat(monkeypatch, status, headers, body):
    class FakeConnection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 8369, 5)

        def request(self, method, path, body, headers):
            assert (method, path) == ("POST", "/chat")
            assert headers["Authorization"] == "Bearer " + ACCESS

        def getresponse(self):
            return self

        def getheader(self, name):
            return headers.get(name)

        def read(self, limit):
            assert limit == pilot.MAX_BODY + 1
            return body[:limit]

        def close(self):
            pass

    FakeConnection.status = status
    monkeypatch.setattr(pilot.http.client, "HTTPConnection", FakeConnection)
    with pytest.raises(ValueError):
        pilot.request("POST", "/chat", ACCESS, {"tools_enabled": False}, 5)


def test_route_rejects_arbitrary_target():
    with pytest.raises(ValueError):
        pilot.request("DELETE", "/history", ACCESS)
