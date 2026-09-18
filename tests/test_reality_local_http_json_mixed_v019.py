import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from phios.mandala import MandalaStatus
from phios.reality import (
    JsonContractClause,
    JsonMixedContractClause,
    LocalHttpObservation,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
)
from phios.spine.runtime import PhiOSSpine


class FakeMixedHttpProvider:
    name = "fake-mixed-http"

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
        b'{"models":[{"name":"alpha"}],"ready":true,'
        b'"queue_depth":7,"load":0.42}'
    ),
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/state",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256="f" * 64,
        body_bytes_observed=0 if body is None else len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=4.5,
        provider="fake-mixed-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T22:00:00+00:00",
        body=body,
    )


def _mixed_clauses() -> tuple[JsonMixedContractClause, ...]:
    return (
        JsonMixedContractClause(
            pointer="/models",
            expected_json_type="array",
        ),
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_gte",
            structural_bound=1,
        ),
        JsonMixedContractClause(
            pointer="/models/0/name",
            structural_predicate="string_non_empty",
        ),
        JsonMixedContractClause(
            pointer="/ready",
            scalar_predicate="boolean_is_true",
        ),
        JsonMixedContractClause(
            pointer="/queue_depth",
            scalar_predicate="integer_lte",
            scalar_operand="10",
        ),
        JsonMixedContractClause(
            pointer="/load",
            scalar_predicate="number_lte",
            scalar_operand="0.5",
        ),
    )


def _structural_only_clauses() -> tuple[JsonMixedContractClause, ...]:
    return (
        JsonMixedContractClause(
            pointer="/models",
            expected_json_type="array",
        ),
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_gte",
            structural_bound=1,
        ),
        JsonMixedContractClause(
            pointer="/models/0/name",
            structural_predicate="string_non_empty",
        ),
    )


def _claim(
    clauses: tuple[JsonMixedContractClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
        statement="The endpoint satisfies one same-snapshot mixed JSON contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=(
            clauses if clauses is not None else _mixed_clauses()
        ),
    )


def _base_permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
    ]


def _value_permissions() -> list[str]:
    return _base_permissions() + [
        "reality.local_http.semantic.value.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="json-mixed-v019",
    )


def test_mixed_clause_requires_exactly_one_mode() -> None:
    empty = JsonMixedContractClause(pointer="/ready")
    two_modes = JsonMixedContractClause(
        pointer="/ready",
        expected_json_type="boolean",
        scalar_predicate="boolean_is_true",
    )

    assert "local_http_json_mixed_clause_requires_exactly_one_mode" in (
        empty.validation_errors()
    )
    assert "local_http_json_mixed_clause_requires_exactly_one_mode" in (
        two_modes.validation_errors()
    )


def test_mixed_clause_mapping_rejects_unknown_keys() -> None:
    try:
        JsonMixedContractClause.from_mapping(
            {
                "pointer": "/ready",
                "scalar_predicte": "boolean_is_true",
            }
        )
    except ValueError as exc:
        assert "unsupported mixed JSON clause keys: scalar_predicte" in str(exc)
    else:
        raise AssertionError("unknown mixed clause key should fail closed")


def test_v017_clause_format_remains_frozen() -> None:
    try:
        JsonContractClause.from_mapping(
            {
                "pointer": "/ready",
                "scalar_predicate": "boolean_is_true",
            }
        )
    except ValueError as exc:
        assert "unsupported JSON clause keys: scalar_predicate" in str(exc)
    else:
        raise AssertionError("v0.17 clause format must not silently expand")


def test_mixed_contract_requires_one_to_eight_clauses() -> None:
    empty = _claim(())
    nine = _claim(
        tuple(
            JsonMixedContractClause(
                pointer=f"/field{i}",
                expected_json_type="string",
            )
            for i in range(9)
        )
    )

    assert "local_http_json_mixed_contract_requires_1_to_8_clauses" in (
        empty.validation_errors()
    )
    assert "local_http_json_mixed_contract_requires_1_to_8_clauses" in (
        nine.validation_errors()
    )


def test_mixed_contract_rejects_legacy_fields() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
        statement="Ambiguous contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_pointer="/ready",
        json_mixed_contract_clauses=_mixed_clauses(),
    )

    assert "local_http_json_mixed_contract_disallows_legacy_fields" in (
        claim.validation_errors()
    )


def test_non_mixed_claim_rejects_mixed_clause_payload() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
        statement="Single scalar predicate.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_pointer="/ready",
        json_scalar_predicate_kind="boolean_is_true",
        json_mixed_contract_clauses=(
            JsonMixedContractClause(
                pointer="/ready",
                scalar_predicate="boolean_is_true",
            ),
        ),
    )

    assert "json_mixed_contract_clauses_only_for_mixed_contract" in (
        claim.validation_errors()
    )


def test_structural_only_mixed_contract_does_not_require_value_grant(
    tmp_path: Path,
) -> None:
    provider = FakeMixedHttpProvider(_observation())
    spine = _spine(tmp_path, _base_permissions())

    result = spine.verify_reality(
        claims=(_claim(_structural_only_clauses()),),
        local_http_provider=provider,
    )

    assert provider.calls == 1
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["requires_value_read"] is False
    assert claim_result["all_clauses_match"] is True


def test_scalar_clause_requires_value_grant_before_io(tmp_path: Path) -> None:
    provider = FakeMixedHttpProvider(_observation())
    spine = _spine(tmp_path, _base_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    claim_result = result.claim_results[0]
    assert claim_result["requires_value_read"] is True
    assert claim_result["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )


def test_mixed_contract_uses_one_observation_for_all_modes(tmp_path: Path) -> None:
    provider = FakeMixedHttpProvider(_observation())
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 1
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["clause_count"] == 6
    assert claim_result["clauses_evaluated"] == 6
    assert claim_result["all_clauses_match"] is True
    assert [item["mode"] for item in claim_result["clause_results"]] == [
        "type",
        "structural",
        "structural",
        "scalar",
        "scalar",
        "scalar",
    ]


def test_mixed_contract_evaluates_all_clauses_after_mismatch(tmp_path: Path) -> None:
    provider = FakeMixedHttpProvider(_observation())
    spine = _spine(tmp_path, _value_permissions())
    clauses = (
        JsonMixedContractClause(
            pointer="/models",
            expected_json_type="object",
        ),
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_gte",
            structural_bound=1,
        ),
        JsonMixedContractClause(
            pointer="/missing",
            expected_json_type="string",
        ),
        JsonMixedContractClause(
            pointer="/ready",
            scalar_predicate="boolean_is_true",
        ),
        JsonMixedContractClause(
            pointer="/queue_depth",
            scalar_predicate="integer_lte",
            scalar_operand="3",
        ),
    )

    result = spine.verify_reality(
        claims=(_claim(clauses),),
        local_http_provider=provider,
    )

    assert provider.calls == 1
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["clauses_evaluated"] == 5
    assert [item["clause_reason"] for item in claim_result["clause_results"]] == [
        "type_mismatch",
        "matches",
        "pointer_missing",
        "matches",
        "predicate_mismatch",
    ]
    assert claim_result["all_clauses_match"] is False


def test_mixed_scalar_observed_value_is_not_persisted(tmp_path: Path) -> None:
    observed_secret = 827364519
    provider = FakeMixedHttpProvider(
        _observation(
            body=json.dumps(
                {
                    "models": [{"name": "alpha"}],
                    "private_metric": observed_secret,
                    "ready": True,
                }
            ).encode("utf-8")
        )
    )
    spine = _spine(tmp_path, _value_permissions())
    clauses = (
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_eq",
            structural_bound=1,
        ),
        JsonMixedContractClause(
            pointer="/private_metric",
            scalar_predicate="integer_gte",
            scalar_operand="1",
        ),
        JsonMixedContractClause(
            pointer="/ready",
            scalar_predicate="boolean_is_true",
        ),
    )

    result = spine.verify_reality(
        claims=(_claim(clauses),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    evidence = json.loads(
        spine.soma.evidence.read_bytes(claim_result["observation_evidence_ref"])
    )
    serialized = json.dumps(evidence, sort_keys=True)

    assert str(observed_secret) not in serialized
    assert "observed_value" not in serialized
    assert "body" not in evidence["http_observation"]
    scalar_result = evidence["semantic_observation"]["clause_results"][1]
    assert scalar_result["mode"] == "scalar"
    assert scalar_result["predicate_matches"] is True
    assert scalar_result["measurement"] is None


def test_mixed_status_mismatch_skips_clause_evaluation(tmp_path: Path) -> None:
    provider = FakeMixedHttpProvider(_observation(status=503))
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    claim_result = result.claim_results[0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    assert claim_result["reason"] == (
        "local_http_json_mixed_contract_status_mismatch"
    )
    assert claim_result["clauses_evaluated"] == 0
    assert claim_result["all_clauses_match"] is None


def test_mixed_truncated_body_is_unresolved(tmp_path: Path) -> None:
    provider = FakeMixedHttpProvider(
        _observation(body=b'{"models":[', truncated=True)
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == (
        "local_http_json_mixed_contract_body_truncated"
    )


class _MixedHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits = 0

    def do_GET(self) -> None:
        type(self).hits += 1
        body = (
            b'{"models":[{"name":"alpha"}],"ready":true,'
            b'"queue_depth":3,"load":0.25}'
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_mixed_server() -> Iterator[tuple[str, int]]:
    _MixedHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MixedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_mixed_contract_uses_exactly_one_http_request(tmp_path: Path) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _value_permissions())

    with _loopback_mixed_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
            statement="The live endpoint satisfies one mixed same-snapshot contract.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_mixed_contract_clauses=_mixed_clauses(),
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _MixedHandler.hits

    assert hits == 1
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["all_clauses_match"] is True
    assert claim_result["requires_value_read"] is True
    assert "mixed_contract_uses_single_observation_snapshot" in (
        result.receipt.limitations
    )
    assert "mixed_contract_scalar_observed_values_not_persisted" in (
        result.receipt.limitations
    )
