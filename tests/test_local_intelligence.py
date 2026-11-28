import json

import pytest

from phios import local_intelligence as li


def test_default_is_offline(monkeypatch):
    def forbidden():
        pytest.fail("unexpected Ollama call")

    monkeypatch.setattr(li, "probe_ollama", forbidden)
    report = li.census()
    assert report["status"] == "REVIEW_ONLY"
    assert report["ollama"]["status"] == "NOT_CHECKED"
    assert report["authority_granted"] is False
    assert report["inference_executed"] is False
    assert report["physical_weights_verified"] is False
    ids = [row["id"] for row in report["registry"]]
    assert len(ids) == len(set(ids))
    assert {"vessie", "gaia", "phibuddy", "braincbrain", "agentora", "model-forge"} <= set(ids)
    assert all(row["verification"] == "documentation_only" for row in report["registry"])
    brain = next(row for row in report["registry"] if row["id"] == "braincbrain")
    assert brain["kind"] == "model_config"


def test_inventory_classifies_cloud_without_claiming_local_bytes():
    rows = li.model_inventory({"models": [
        {"name": "qwen3:4b", "size": 123},
        {"name": "foo-cloud", "size": 0},
        {"model": "remote:latest", "remote_host": "example.invalid"},
        {"name": "unknown:latest"},
    ]})
    assert [r["name"] for r in rows] == sorted(r["name"] for r in rows)
    by_name = {r["name"]: r for r in rows}
    assert by_name["qwen3:4b"]["location"] == "UNVERIFIED"
    assert by_name["foo-cloud"]["location"] == "CLOUD_REFERENCE"
    assert by_name["remote:latest"]["location"] == "CLOUD_REFERENCE"
    assert by_name["unknown:latest"]["declared_bytes"] is None


@pytest.mark.parametrize("payload", [
    None, {}, {"models": {}}, {"models": [None]},
    {"models": [{"name": ""}]},
    {"models": [{"name": "a", "size": True}]},
    {"models": [{"name": "a", "size": -1}]},
    {"models": [{"name": "a"}, {"name": "a"}]},
])
def test_reject_bad_inventory(payload):
    with pytest.raises(ValueError):
        li.model_inventory(payload)


@pytest.mark.parametrize(("status", "body", "expected"), [
    (200, b'{"models":[]}', "API_REPORTED"),
    (200, b"not-json", "INVALID_RESPONSE"),
    (200, b"x" * (li.MAX_RESPONSE + 1), "INVALID_RESPONSE"),
    (302, b"", "HTTP_ERROR"),
    (503, b"", "HTTP_ERROR"),
])
def test_probe_fixed_read_only_request(monkeypatch, status, body, expected):
    calls = []

    class FakeConnection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 11434, 2)

        def request(self, method, path, headers):
            calls.append((method, path))
            assert headers == {"Accept": "application/json"}

        def getresponse(self):
            return self

        def read(self, limit):
            assert limit == li.MAX_RESPONSE + 1
            return body[:limit]

        def close(self):
            calls.append("closed")

    FakeConnection.status = status
    monkeypatch.setattr(li.http.client, "HTTPConnection", FakeConnection)
    report = li.census(True)
    assert report["ollama"]["status"] == expected
    assert report["inference_executed"] is False
    assert calls == [("GET", "/api/tags"), "closed"]


def test_cli_default(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["local_intelligence"])
    li.main()
    assert json.loads(capsys.readouterr().out)["ollama"]["status"] == "NOT_CHECKED"
