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
    evaluate_json_structural_predicate,
    json_structural_predicate_error,
)
from phios.spine.runtime import PhiOSSpine


class FakePredicateHttpProvider:
    name = "fake-predicate-http"

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
    body: bytes | None = b'{"models":[{"name":"a"},{"name":"b"}]}',
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/tags",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256="c" * 64,
        body_bytes_observed=0 if body is None else len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=2.5,
        provider="fake-predicate-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T19:00:00+00:00",
        body=body,
    )


def _claim(
    *,
    pointer: str = "/models",
    predicate: str = "array_length_gte",
    bound: int | None = 1,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
        statement="The local endpoint satisfies the bounded structural JSON predicate.",
        http_url="http://127.0.0.1:11434/api/tags",
        expected_http_status=200,
        json_pointer=pointer,
        json_predicate_kind=predicate,
        json_predicate_bound=bound,
    )


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="json-predicate-v016",
    )


def _permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
    ]


def test_structural_predicate_contract_validation_is_bounded() -> None:
    assert json_structural_predicate_error("string_non_empty", None) is None
    assert json_structural_predicate_error("string_non_empty", 1) == (
        "local_http_json_predicate_disallows_bound"
    )
    assert json_structural_predicate_error("array_length_gte", None) == (
        "local_http_json_predicate_requires_bound"
    )
    assert json_structural_predicate_error("array_length_gte", 1_000_001) == (
        "local_http_json_predicate_invalid_bound"
    )
    assert json_structural_predicate_error("anything_goes", 1) == (
        "local_http_json_predicate_invalid_kind"
    )


def test_structural_predicate_helper_preserves_type_boundary() -> None:
    matched = evaluate_json_structural_predicate(
        ["a", "b"],
        predicate="array_length_gte",
        bound=2,
    )
    wrong_type = evaluate_json_structural_predicate(
        {"a": 1, "b": 2},
        predicate="array_length_gte",
        bound=2,
    )

    assert matched["type_matches"] is True
    assert matched["measurement_name"] == "array_length"
    assert matched["measurement"] == 2
    assert matched["predicate_matches"] is True

    assert wrong_type["expected_json_type"] == "array"
    assert wrong_type["observed_json_type"] == "object"
    assert wrong_type["type_matches"] is False
    assert wrong_type["predicate_matches"] is False


def test_json_predicate_requires_semantic_grant_before_io(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(_observation())
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


def test_array_length_gte_predicate_is_supported(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(predicate="array_length_gte", bound=2),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["expected_json_type"] == "array"
    assert claim_result["observed_json_type"] == "array"
    assert claim_result["measurement_name"] == "array_length"
    assert claim_result["measurement"] == 2
    assert claim_result["predicate_matches"] is True


def test_array_length_predicate_false_is_contradicted(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(predicate="array_length_gte", bound=3),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["reason"] == "local_http_json_predicate_mismatch"
    assert claim_result["measurement"] == 2
    assert claim_result["predicate_matches"] is False


def test_object_key_count_predicate_is_supported(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(
        _observation(body=b'{"meta":{"one":1,"two":2}}')
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                pointer="/meta",
                predicate="object_key_count_eq",
                bound=2,
            ),
        ),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["measurement_name"] == "object_key_count"
    assert claim_result["measurement"] == 2


def test_predicate_wrong_type_is_distinct_from_false_predicate(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(
        _observation(body=b'{"models":{"one":1,"two":2}}')
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(predicate="array_length_gte", bound=1),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["reason"] == "local_http_json_predicate_type_mismatch"
    assert claim_result["observed_json_type"] == "object"
    assert claim_result["measurement"] is None


def test_string_non_empty_does_not_persist_string_value(tmp_path: Path) -> None:
    secret = "do-not-persist-this-token-value"
    provider = FakePredicateHttpProvider(
        _observation(body=json.dumps({"token": secret}).encode("utf-8"))
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                pointer="/token",
                predicate="string_non_empty",
                bound=None,
            ),
        ),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["measurement_name"] == "is_non_empty"
    assert claim_result["measurement"] is True

    evidence = json.loads(
        spine.soma.evidence.read_bytes(claim_result["observation_evidence_ref"])
    )
    serialized = json.dumps(evidence, sort_keys=True)
    assert secret not in serialized
    assert "body" not in evidence["http_observation"]
    assert evidence["semantic_observation"]["measurement"] is True


def test_empty_string_predicate_is_contradicted(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(_observation(body=b'{"token":""}'))
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                pointer="/token",
                predicate="string_non_empty",
                bound=None,
            ),
        ),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["reason"] == "local_http_json_predicate_mismatch"


def test_truncated_predicate_body_is_unresolved(tmp_path: Path) -> None:
    provider = FakePredicateHttpProvider(
        _observation(body=b'{"models":[', truncated=True)
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == (
        "local_http_json_predicate_body_truncated"
    )


class _PredicateHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b'{"models":[{"name":"alpha"},{"name":"beta"}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_predicate_server() -> Iterator[tuple[str, int]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PredicateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_loopback_structural_predicate_receipt(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _permissions())

    with _loopback_predicate_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
            statement="The live local endpoint exposes at least one model.",
            http_url=f"http://{host}:{port}/api/tags",
            expected_http_status=200,
            json_pointer="/models",
            json_predicate_kind="array_length_gte",
            json_predicate_bound=1,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["measurement"] == 2
    assert claim_result["predicate_matches"] is True
    assert "json_structural_predicate_is_not_application_health" in (
        result.receipt.limitations
    )
