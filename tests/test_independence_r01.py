import json
from pathlib import Path
import importlib.util
from unittest.mock import Mock, patch

import pytest

spec = importlib.util.spec_from_file_location(
    "independence_r01", Path(__file__).resolve().parents[1] / "scripts" / "independence_r01.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_inventory_no_network(capsys):
    with patch.object(mod.http.client, "HTTPConnection") as conn:
        assert mod.main([]) == 0
        conn.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert report["inference"]["status"] == "NOT_RUN"
    assert report["offline_verified"] is False
    assert report["certification"] == "UNVERIFIED"


def test_requires_explicit_confirmation():
    with patch.object(mod.http.client, "HTTPConnection") as conn:
        with pytest.raises(SystemExit) as e:
            mod.main(["--model", "test:local"])
        assert e.value.code == 2
        conn.assert_not_called()


@pytest.mark.parametrize("status,body,expected", [
    (200, {"done": True, "model": "test:local", "response": "PHI_LOCAL_OK"}, "PASS"),
    (200, {"done": False, "model": "test:local", "response": "PHI_LOCAL_OK"}, "FAIL"),
    (200, {"done": True, "model": "other:local", "response": "PHI_LOCAL_OK"}, "FAIL"),
    (200, {"done": True, "model": "test:local", "response": "wrong"}, "FAIL"),
    (302, {}, "FAIL"),
    (500, {}, "FAIL"),
])
def test_inference(status, body, expected):
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        conn = factory.return_value
        response = conn.getresponse.return_value
        response.status = status
        response.read.return_value = json.dumps(body).encode()
        assert mod.smoke("test:local")["status"] == expected
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=120)
        conn.request.assert_called_once()
        assert conn.request.call_args.args[:2] == ("POST", "/api/generate")
        conn.close.assert_called_once()


def test_transport_failure():
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        factory.return_value.request.side_effect = TimeoutError
        assert mod.smoke("test:local")["status"] == "FAIL"


def test_response_limit():
    with patch.object(mod.http.client, "HTTPConnection") as factory:
        response = factory.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b"x" * (mod.MAX_RESPONSE + 1)
        assert mod.smoke("test:local")["reason"] == "RESPONSE_LIMIT"
