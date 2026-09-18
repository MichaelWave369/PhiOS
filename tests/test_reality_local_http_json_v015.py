import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from phios.mandala import MandalaStatus
from phios.reality import (
    LocalHttpObservation,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
    json_pointer_error,
    resolve_json_pointer,
)
from phios.spine.runtime import PhiOSSpine


class FakeJsonHttpProvider:
    name = "fake-json-http"

    def __init__(self, observation: LocalHttpObservation) -> None:
        self.observation = observation
        self.calls = 0

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        self.calls += 1
        return self.observation


def _observation(
    *,
    body: bytes | None = b'{"version":"1.2.3"}',
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/version",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256="b" * 64,
        body_bytes_observed=0 if body is None else len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=3.5,
        provider="fake-json-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T18:00:00+00:00",
        body=body,
    )


def _claim(
    *,
    pointer: str = "/version",
    expected_type: str = "string",
    expected_status: int = 200,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
        statement="The local version endpoint returns JSON with a string version field.",
        http_url="http://127.0.0.1:11434/api/version",
        expected_http_status=expected_status,
        json_pointer=pointer,
        expected_json_type=expected_type,
    )


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="json-contract-v015",
    )


def test_json_contract_requires_separate_semantic_grant(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation())
    spine = _spine(
        tmp_path,
        ["reality.verify", "reality.local_http.read"],
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.read"
    )
    assert provider.calls == 0


def test_json_contract_supports_valid_pointer_and_type(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation())
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["json_valid"] is True
    assert claim_result["pointer_exists"] is True
    assert claim_result["observed_json_type"] == "string"
    assert claim_result["type_matches"] is True

    evidence_ref = claim_result["observation_evidence_ref"]
    evidence = json.loads(spine.soma.evidence.read_bytes(evidence_ref))
    assert "body" not in evidence["http_observation"]
    assert evidence["semantic_observation"]["observed_json_type"] == "string"
    assert evidence["semantic_contract"]["json_pointer"] == "/version"


def test_json_contract_missing_pointer_is_contradicted(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation())
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(pointer="/missing"),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["reason"] == (
        "local_http_json_contract_pointer_missing"
    )


def test_json_contract_type_mismatch_is_contradicted(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation())
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(expected_type="integer"),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["observed_json_type"] == "string"
    assert result.claim_results[0]["type_matches"] is False


def test_json_contract_invalid_json_is_contradicted(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation(body=b'{"version":'))
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["json_valid"] is False
    assert result.claim_results[0]["reason"] == "local_http_json_contract_invalid_json"


def test_json_contract_rejects_nonstandard_nan_json(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(_observation(body=b'{"version":NaN}'))
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(expected_type="number"),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["reason"] == "local_http_json_contract_invalid_json"


def test_json_contract_truncated_body_is_unresolved(tmp_path: Path) -> None:
    provider = FakeJsonHttpProvider(
        _observation(body=b'{"version":"1', truncated=True)
    )
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.claim_results[0]["reason"] == (
        "local_http_json_contract_body_truncated"
    )


def test_json_contract_status_mismatch_is_contradicted_without_semantic_guess(
    tmp_path: Path,
) -> None:
    provider = FakeJsonHttpProvider(_observation(status=503))
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    result = spine.verify_reality(
        claims=(_claim(expected_status=200),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["reason"] == "local_http_json_contract_status_mismatch"
    assert claim_result["json_valid"] is None
    assert claim_result["pointer_exists"] is None


def test_json_pointer_supports_escaped_object_keys_and_arrays() -> None:
    document = {"a/b": {"~key": [{"value": 7}]}}
    pointer = "/a~1b/~0key/0/value"

    assert json_pointer_error(pointer) is None
    exists, value = resolve_json_pointer(document, pointer)

    assert exists is True
    assert value == 7


def test_json_pointer_rejects_invalid_escape() -> None:
    assert json_pointer_error("/bad~2escape") == (
        "local_http_json_claim_invalid_pointer_escape"
    )


class _JsonHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b'{"version":"0.15-test","models":3}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_json_server() -> Iterator[tuple[str, int]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JsonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_stdlib_body_is_used_semantically_but_not_persisted(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(
        tmp_path,
        [
            "reality.verify",
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ],
    )

    with _loopback_json_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
            statement="The live local endpoint exposes a string version field.",
            http_url=f"http://{host}:{port}/version",
            expected_http_status=200,
            json_pointer="/version",
            expected_json_type="string",
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    evidence = json.loads(
        spine.soma.evidence.read_bytes(claim_result["observation_evidence_ref"])
    )
    assert "body" not in evidence["http_observation"]
    assert evidence["semantic_observation"] == {
        "json_valid": True,
        "observed_json_type": "string",
        "pointer_exists": True,
        "type_matches": True,
    }
