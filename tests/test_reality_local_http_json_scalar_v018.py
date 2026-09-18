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
    evaluate_json_scalar_predicate,
    json_scalar_predicate_error,
)
from phios.spine.runtime import PhiOSSpine


class FakeScalarHttpProvider:
    name = "fake-scalar-http"

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
    body: bytes | None = b'{"ready":true,"queue_depth":7,"load":0.42}',
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/state",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256="e" * 64,
        body_bytes_observed=0 if body is None else len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=3.5,
        provider="fake-scalar-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T21:00:00+00:00",
        body=body,
    )


def _claim(
    *,
    pointer: str = "/ready",
    predicate: str = "boolean_is_true",
    operand: str | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
        statement="The local endpoint satisfies one bounded scalar predicate.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_pointer=pointer,
        json_scalar_predicate_kind=predicate,
        json_scalar_operand=operand,
    )


def _permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
        "reality.local_http.semantic.value.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="json-scalar-v018",
    )


def test_scalar_predicate_contract_validation_is_bounded() -> None:
    assert json_scalar_predicate_error("boolean_is_true", None) is None
    assert json_scalar_predicate_error("boolean_is_true", "1") == (
        "local_http_json_scalar_predicate_disallows_operand"
    )
    assert json_scalar_predicate_error("integer_gte", None) == (
        "local_http_json_scalar_predicate_requires_operand"
    )
    assert json_scalar_predicate_error("integer_gte", "1.5") == (
        "local_http_json_scalar_predicate_requires_integer_operand"
    )
    assert json_scalar_predicate_error("number_lte", "NaN") == (
        "local_http_json_scalar_predicate_invalid_operand"
    )
    assert json_scalar_predicate_error("arbitrary_eval", "1") == (
        "local_http_json_scalar_predicate_invalid_kind"
    )


def test_scalar_helper_preserves_type_boundary_and_value_privacy() -> None:
    matched = evaluate_json_scalar_predicate(
        7,
        predicate="integer_gte",
        operand="5",
    )
    wrong_type = evaluate_json_scalar_predicate(
        "7",
        predicate="integer_gte",
        operand="5",
    )

    assert matched == {
        "predicate": "integer_gte",
        "expected_json_type": "integer",
        "observed_json_type": "integer",
        "type_matches": True,
        "predicate_matches": True,
    }
    assert "observed_value" not in matched
    assert wrong_type["observed_json_type"] == "string"
    assert wrong_type["type_matches"] is False
    assert wrong_type["predicate_matches"] is False


def test_scalar_predicate_requires_value_read_grant_before_io(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(_observation())
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

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )
    assert provider.calls == 0


def test_boolean_true_predicate_is_supported(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["observed_json_type"] == "boolean"
    assert claim_result["predicate_matches"] is True
    assert "observed_value" not in claim_result


def test_boolean_false_predicate_can_contradict(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(predicate="boolean_is_false"),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["reason"] == (
        "local_http_json_scalar_predicate_mismatch"
    )


def test_integer_and_number_predicates_are_supported(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())
    integer_claim = _claim(
        pointer="/queue_depth",
        predicate="integer_lte",
        operand="10",
    )
    number_claim = _claim(
        pointer="/load",
        predicate="number_lte",
        operand="0.5",
    )

    result = spine.verify_reality(
        claims=(integer_claim, number_claim),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert [item["predicate_matches"] for item in result.claim_results] == [
        True,
        True,
    ]
    assert provider.calls == 2


def test_scalar_wrong_type_is_distinct_from_false_predicate(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(
        _observation(body=b'{"queue_depth":"7"}')
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                pointer="/queue_depth",
                predicate="integer_gte",
                operand="5",
            ),
        ),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["reason"] == "local_http_json_scalar_predicate_type_mismatch"
    assert claim_result["observed_json_type"] == "string"


def test_observed_numeric_scalar_is_not_persisted(tmp_path: Path) -> None:
    observed_secret = 918273645
    provider = FakeScalarHttpProvider(
        _observation(
            body=json.dumps({"private_metric": observed_secret}).encode("utf-8")
        )
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                pointer="/private_metric",
                predicate="integer_gte",
                operand="1",
            ),
        ),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    evidence = json.loads(
        spine.soma.evidence.read_bytes(claim_result["observation_evidence_ref"])
    )
    serialized = json.dumps(evidence, sort_keys=True)

    assert str(observed_secret) not in serialized
    assert "body" not in evidence["http_observation"]
    assert "observed_value" not in serialized
    assert evidence["semantic_observation"]["predicate_matches"] is True


def test_scalar_status_mismatch_skips_value_evaluation(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(_observation(status=503))
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    claim_result = result.claim_results[0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    assert claim_result["reason"] == (
        "local_http_json_scalar_predicate_status_mismatch"
    )
    assert claim_result["observed_json_type"] is None
    assert claim_result["predicate_matches"] is None


def test_scalar_truncated_body_is_unresolved(tmp_path: Path) -> None:
    provider = FakeScalarHttpProvider(
        _observation(body=b'{"ready":tr', truncated=True)
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == (
        "local_http_json_scalar_predicate_body_truncated"
    )


class _ScalarHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b'{"ready":true,"queue_depth":3}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_scalar_server() -> Iterator[tuple[str, int]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ScalarHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_loopback_scalar_predicate_receipt(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _permissions())

    with _loopback_scalar_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
            statement="The live local endpoint reports ready true.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_pointer="/ready",
            json_scalar_predicate_kind="boolean_is_true",
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["predicate_matches"] is True
    assert "scalar_value_read_requires_separate_grant" in result.receipt.limitations
    assert "scalar_predicate_observed_value_not_persisted" in result.receipt.limitations
