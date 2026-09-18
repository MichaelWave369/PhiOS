import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from phios.mandala import MandalaStatus
from phios.reality import (
    JsonContractClause,
    LocalHttpObservation,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
)
from phios.spine.runtime import PhiOSSpine


class FakeMultiHttpProvider:
    name = "fake-multi-http"

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
    body: bytes | None = (
        b'{"models":[{"name":"alpha"},{"name":"beta"}],"version":"1.2.3"}'
    ),
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/tags",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256="d" * 64,
        body_bytes_observed=0 if body is None else len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=4.0,
        provider="fake-multi-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T20:00:00+00:00",
        body=body,
    )


def _clauses() -> tuple[JsonContractClause, ...]:
    return (
        JsonContractClause(pointer="/models", expected_json_type="array"),
        JsonContractClause(
            pointer="/models",
            predicate="array_length_gte",
            bound=1,
        ),
        JsonContractClause(pointer="/models/0/name", expected_json_type="string"),
        JsonContractClause(
            pointer="/models/0/name",
            predicate="string_non_empty",
        ),
    )


def _claim(
    clauses: tuple[JsonContractClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
        statement="The local tags endpoint satisfies one bounded multi-clause contract.",
        http_url="http://127.0.0.1:11434/api/tags",
        expected_http_status=200,
        json_contract_clauses=clauses if clauses is not None else _clauses(),
    )


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="json-multi-v017",
    )


def _permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
    ]


def test_multi_contract_requires_one_to_eight_clauses() -> None:
    empty = _claim(())
    nine = _claim(
        tuple(
            JsonContractClause(pointer=f"/field{i}", expected_json_type="string")
            for i in range(9)
        )
    )

    assert "local_http_json_multi_contract_requires_1_to_8_clauses" in (
        empty.validation_errors()
    )
    assert "local_http_json_multi_contract_requires_1_to_8_clauses" in (
        nine.validation_errors()
    )


def test_multi_contract_rejects_mixed_single_clause_fields() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
        statement="Ambiguous contract.",
        http_url="http://127.0.0.1:11434/api/tags",
        expected_http_status=200,
        json_pointer="/models",
        json_contract_clauses=_clauses(),
    )

    assert "local_http_json_multi_contract_disallows_single_fields" in (
        claim.validation_errors()
    )


def test_non_multi_claim_rejects_multi_clause_payload() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
        statement="Single clause.",
        http_url="http://127.0.0.1:11434/api/tags",
        expected_http_status=200,
        json_pointer="/models",
        expected_json_type="array",
        json_contract_clauses=(
            JsonContractClause(pointer="/models", expected_json_type="array"),
        ),
    )

    assert "json_contract_clauses_only_for_multi_contract" in (
        claim.validation_errors()
    )


def test_clause_mapping_rejects_unknown_keys() -> None:
    try:
        JsonContractClause.from_mapping(
            {
                "pointer": "/models",
                "predicte": "array_length_gte",
                "bound": 1,
            }
        )
    except ValueError as exc:
        assert "unsupported JSON clause keys: predicte" in str(exc)
    else:
        raise AssertionError("unknown clause key should fail closed")


def test_clause_requires_exactly_one_mode() -> None:
    neither = JsonContractClause(pointer="/models")
    both = JsonContractClause(
        pointer="/models",
        expected_json_type="array",
        predicate="array_length_gte",
        bound=1,
    )

    assert "local_http_json_multi_clause_requires_exactly_one_mode" in (
        neither.validation_errors()
    )
    assert "local_http_json_multi_clause_requires_exactly_one_mode" in (
        both.validation_errors()
    )


def test_multi_contract_requires_semantic_grant_before_io(tmp_path: Path) -> None:
    provider = FakeMultiHttpProvider(_observation())
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


def test_multi_contract_uses_one_observation_for_all_clauses(tmp_path: Path) -> None:
    provider = FakeMultiHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 1
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["clause_count"] == 4
    assert claim_result["clauses_evaluated"] == 4
    assert claim_result["all_clauses_match"] is True
    assert all(
        item["clause_reason"] == "matches"
        for item in claim_result["clause_results"]
    )


def test_multi_contract_evaluates_all_clauses_when_one_fails(tmp_path: Path) -> None:
    provider = FakeMultiHttpProvider(_observation())
    spine = _spine(tmp_path, _permissions())
    clauses = (
        JsonContractClause(pointer="/models", expected_json_type="object"),
        JsonContractClause(
            pointer="/models",
            predicate="array_length_gte",
            bound=1,
        ),
        JsonContractClause(pointer="/missing", expected_json_type="string"),
        JsonContractClause(
            pointer="/version",
            predicate="string_non_empty",
        ),
    )

    result = spine.verify_reality(
        claims=(_claim(clauses),),
        local_http_provider=provider,
    )

    assert provider.calls == 1
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["clauses_evaluated"] == 4
    reasons = [item["clause_reason"] for item in claim_result["clause_results"]]
    assert reasons == [
        "type_mismatch",
        "matches",
        "pointer_missing",
        "matches",
    ]
    assert claim_result["all_clauses_match"] is False


def test_multi_contract_does_not_persist_pointed_string_values(tmp_path: Path) -> None:
    secret = "super-secret-value-that-must-not-land-in-evidence"
    provider = FakeMultiHttpProvider(
        _observation(
            body=json.dumps(
                {
                    "token": secret,
                    "items": ["alpha", "beta"],
                }
            ).encode("utf-8")
        )
    )
    spine = _spine(tmp_path, _permissions())
    clauses = (
        JsonContractClause(
            pointer="/token",
            predicate="string_non_empty",
        ),
        JsonContractClause(
            pointer="/items",
            predicate="array_length_eq",
            bound=2,
        ),
    )

    result = spine.verify_reality(
        claims=(_claim(clauses),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    evidence_ref = result.claim_results[0]["observation_evidence_ref"]
    evidence = json.loads(spine.soma.evidence.read_bytes(evidence_ref))
    serialized = json.dumps(evidence, sort_keys=True)

    assert secret not in serialized
    assert "body" not in evidence["http_observation"]
    assert evidence["semantic_observation"]["all_clauses_match"] is True
    assert evidence["semantic_observation"]["clause_results"][0]["measurement"] is True
    assert evidence["semantic_observation"]["clause_results"][1]["measurement"] == 2


def test_multi_contract_status_mismatch_skips_clause_evaluation(tmp_path: Path) -> None:
    provider = FakeMultiHttpProvider(_observation(status=503))
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    claim_result = result.claim_results[0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    assert claim_result["reason"] == "local_http_json_multi_contract_status_mismatch"
    assert claim_result["clauses_evaluated"] == 0
    assert claim_result["all_clauses_match"] is None


def test_multi_contract_truncated_body_is_unresolved(tmp_path: Path) -> None:
    provider = FakeMultiHttpProvider(
        _observation(body=b'{"models":[', truncated=True)
    )
    spine = _spine(tmp_path, _permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == (
        "local_http_json_multi_contract_body_truncated"
    )


class _MultiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits = 0

    def do_GET(self) -> None:
        type(self).hits += 1
        body = b'{"models":[{"name":"alpha"}],"version":"0.17-test"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_multi_server() -> Iterator[tuple[str, int]]:
    _MultiHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MultiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_multi_contract_uses_exactly_one_http_request(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _permissions())

    with _loopback_multi_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
            statement="The live endpoint satisfies four same-snapshot clauses.",
            http_url=f"http://{host}:{port}/api/tags",
            expected_http_status=200,
            json_contract_clauses=_clauses(),
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _MultiHandler.hits

    assert hits == 1
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["all_clauses_match"] is True
    assert "multi_clause_results_share_one_point_in_time_observation" in (
        result.receipt.limitations
    )
