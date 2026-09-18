import json
import threading
from contextlib import contextmanager
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from phios.mandala import MandalaStatus
from phios.reality import (
    JsonNumericTransitionClause,
    LocalHttpObservation,
    LocalHttpObservationError,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
    evaluate_json_numeric_transition_pair,
    extract_json_numeric_transition_value,
    strict_json_loads,
)
from phios.spine.runtime import PhiOSSpine


class SequenceHttpProvider:
    name = "numeric-transition-sequence-http"

    def __init__(
        self,
        items: list[LocalHttpObservation | Exception],
    ) -> None:
        self.items = list(items)
        self.calls = 0

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        index = self.calls
        self.calls += 1
        item = self.items[index]
        if isinstance(item, Exception):
            raise item
        return item


def _observation(
    index: int,
    value: int | float,
    *,
    pointer_name: str = "counter",
    status: int = 200,
) -> LocalHttpObservation:
    body = json.dumps(
        {
            pointer_name: value,
            "ready": True,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/state",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256=f"{index + 41:064x}",
        body_bytes_observed=len(body),
        body_truncated=False,
        body_digest_scope="full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=1.0 + index,
        provider="numeric-transition-sequence-http",
        provider_version="1.0",
        captured_at_utc=f"2026-09-18T23:20:0{index}+00:00",
        body=body,
    )


def _clause(
    predicate: str = "integer_strictly_increasing",
    *,
    pointer: str = "/counter",
) -> JsonNumericTransitionClause:
    return JsonNumericTransitionClause(
        pointer=pointer,
        predicate=predicate,
    )


def _claim(
    *,
    count: int | None = 3,
    clauses: tuple[JsonNumericTransitionClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_NUMERIC_TRANSITION_CONTRACT,
        statement="The numeric field follows the admitted adjacent transition rule.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_numeric_transition_clauses=(
            clauses if clauses is not None else (_clause(),)
        ),
        repeat_observation_count=count,
    )


def _base_permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
        "reality.local_http.repeat.read",
    ]


def _value_permissions() -> list[str]:
    return _base_permissions() + [
        "reality.local_http.semantic.value.read",
    ]


def _transition_permissions() -> list[str]:
    return _value_permissions() + [
        "reality.local_http.semantic.transition.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="numeric-transition-v024",
    )


def test_transition_clause_validation_and_mapping() -> None:
    clause = JsonNumericTransitionClause.from_mapping(
        {
            "pointer": "/queue_depth",
            "predicate": "integer_non_increasing",
        }
    )

    assert clause.validation_errors() == ()
    assert clause.expected_json_type == "integer"
    assert clause.to_dict() == {
        "pointer": "/queue_depth",
        "predicate": "integer_non_increasing",
        "expected_json_type": "integer",
    }

    invalid = JsonNumericTransitionClause(
        pointer="/counter",
        predicate="integer_magically_better",
    )
    assert "local_http_json_numeric_transition_invalid_predicate" in (
        invalid.validation_errors()
    )


def test_transition_clause_unknown_keys_fail_closed() -> None:
    try:
        JsonNumericTransitionClause.from_mapping(
            {
                "pointer": "/counter",
                "predicate": "integer_non_decreasing",
                "expression": "counter + 1",
            }
        )
    except ValueError as exc:
        assert "unsupported numeric transition clause keys" in str(exc)
    else:
        raise AssertionError("unknown transition key should fail closed")


def test_transition_contract_requires_two_to_five_observations() -> None:
    error = (
        "local_http_json_numeric_transition_contract_requires_2_to_5_observations"
    )
    assert error in _claim(count=1).validation_errors()
    assert error in _claim(count=6).validation_errors()
    assert error in _claim(count=None).validation_errors()
    assert _claim(count=2).validation_errors() == ()
    assert _claim(count=5).validation_errors() == ()


def test_transition_contract_requires_one_to_eight_clauses() -> None:
    empty = _claim(clauses=())
    nine = _claim(
        clauses=tuple(
            _clause(pointer=f"/counter{index}")
            for index in range(9)
        )
    )
    error = "local_http_json_numeric_transition_contract_requires_1_to_8_clauses"
    assert error in empty.validation_errors()
    assert error in nine.validation_errors()


def test_transition_contract_rejects_timing_and_mixed_fields() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_NUMERIC_TRANSITION_CONTRACT,
        statement="Ambiguous transition contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_numeric_transition_clauses=(_clause(),),
        repeat_observation_count=3,
        minimum_interval_seconds=1.0,
    )

    errors = claim.validation_errors()
    assert "minimum_interval_seconds_only_for_timed_mixed_contract" in errors


def test_transition_fields_rejected_on_v023_claim() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_TEMPORAL_ENVELOPE_MIXED_CONTRACT,
        statement="Envelope, not transition semantics.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        repeat_observation_count=3,
        minimum_interval_seconds=1.0,
        maximum_interval_seconds=2.0,
        minimum_series_span_seconds=2.0,
        maximum_series_span_seconds=4.0,
        json_numeric_transition_clauses=(_clause(),),
    )

    assert (
        "json_numeric_transition_clauses_only_for_numeric_transition_contract"
        in claim.validation_errors()
    )


def test_value_grant_required_before_io(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [_observation(0, 1), _observation(1, 2), _observation(2, 3)]
    )
    spine = _spine(tmp_path, _base_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )


def test_transition_grant_required_before_io(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [_observation(0, 1), _observation(1, 2), _observation(2, 3)]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.transition.read"
    )


def test_strictly_increasing_integer_series_is_supported(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [_observation(0, 1), _observation(1, 2), _observation(2, 4)]
    )
    spine = _spine(tmp_path, _transition_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["transition_supported_count"] == 2
    assert claim_result["transition_contradicted_count"] == 0
    assert claim_result["all_transitions_match"] is True
    pairs = claim_result["transition_clause_results"][0]["pair_results"]
    assert [pair["relation"] for pair in pairs] == ["increase", "increase"]


def test_non_decreasing_allows_equal_but_strictly_increasing_does_not(
    tmp_path: Path,
) -> None:
    observations = [
        _observation(0, 1),
        _observation(1, 1),
        _observation(2, 2),
    ]

    non_decreasing = _spine(
        tmp_path / "non-decreasing",
        _transition_permissions(),
    ).verify_reality(
        claims=(
            _claim(
                clauses=(_clause("integer_non_decreasing"),),
            ),
        ),
        local_http_provider=SequenceHttpProvider(observations),
    )
    assert non_decreasing.receipt.status is MandalaStatus.ACCEPTED
    assert (
        non_decreasing.claim_results[0]["transition_clause_results"][0][
            "pair_results"
        ][0]["relation"]
        == "equal"
    )

    strict = _spine(
        tmp_path / "strict",
        _transition_permissions(),
    ).verify_reality(
        claims=(_claim(),),
        local_http_provider=SequenceHttpProvider(observations),
    )
    assert strict.receipt.status is MandalaStatus.DISPUTED
    assert strict.claim_results[0]["transition_contradicted_count"] == 1


def test_number_transition_accepts_integer_and_json_number(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0, 1),
            _observation(1, 1.5),
            _observation(2, 2),
        ]
    )
    spine = _spine(tmp_path, _transition_permissions())
    claim = _claim(
        clauses=(_clause("number_strictly_increasing"),),
    )

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    pairs = result.claim_results[0]["transition_clause_results"][0]["pair_results"]
    assert pairs[0]["left_observed_json_type"] == "integer"
    assert pairs[0]["right_observed_json_type"] == "number"
    assert pairs[1]["left_observed_json_type"] == "number"
    assert pairs[1]["right_observed_json_type"] == "integer"


def test_integer_transition_rejects_json_number_input(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0, 1),
            _observation(1, 1.5),
            _observation(2, 2),
        ]
    )
    spine = _spine(tmp_path, _transition_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["sample_contradicted_count"] == 1
    assert claim_result["transition_contradicted_count"] == 2


def test_extract_and_pair_helpers_do_not_return_raw_values_in_metadata() -> None:
    document = strict_json_loads(b'{"counter":918273645}')
    clause = _clause("integer_strictly_increasing")
    metadata, transient_value = extract_json_numeric_transition_value(
        document,
        clause,
    )

    assert transient_value == 918273645
    assert "observed_value" not in metadata
    assert "value" not in metadata

    comparison = evaluate_json_numeric_transition_pair(
        918273645,
        918273646,
        predicate="integer_strictly_increasing",
    )
    assert comparison["relation"] == "increase"
    assert comparison["predicate_matches"] is True
    assert "observed_value" not in comparison
    assert "left_value" not in comparison
    assert "right_value" not in comparison


def test_timeout_keeps_adjacent_pairs_unresolved_and_all_samples_are_attempted(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0, 1),
            LocalHttpObservationError("local_http_timeout", "timed out"),
            _observation(2, 3),
        ]
    )
    spine = _spine(tmp_path, _transition_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.UNKNOWN
    claim_result = result.claim_results[0]
    assert claim_result["transition_unresolved_count"] == 2
    assert claim_result["sample_results"][1]["observation_evidence_ref"] is None


def test_transition_contradiction_precedes_unresolved(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0, 3),
            _observation(1, 2),
            LocalHttpObservationError("local_http_timeout", "timed out"),
        ]
    )
    spine = _spine(tmp_path, _transition_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["transition_contradicted_count"] >= 1
    assert claim_result["transition_unresolved_count"] >= 1
    assert claim_result["reason"] == (
        "local_http_json_numeric_transition_contradiction"
    )


def test_transition_values_do_not_persist_in_sample_or_series_evidence(
    tmp_path: Path,
) -> None:
    secrets = [918273641, 918273642, 918273643]
    provider = SequenceHttpProvider(
        [
            _observation(index, secret)
            for index, secret in enumerate(secrets)
        ]
    )
    spine = _spine(tmp_path, _transition_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    refs = list(claim_result["sample_evidence_refs"]) + [
        claim_result["series_evidence_ref"]
    ]
    for evidence_ref in refs:
        serialized = spine.soma.evidence.read_bytes(evidence_ref).decode("utf-8")
        assert "observed_value" not in serialized
        for secret in secrets:
            assert str(secret) not in serialized


def test_decimal_transition_helper_is_exact() -> None:
    comparison = evaluate_json_numeric_transition_pair(
        Decimal("0.1"),
        Decimal("0.1000000000000000001"),
        predicate="number_strictly_increasing",
    )
    assert comparison["relation"] == "increase"
    assert comparison["predicate_matches"] is True


class _TransitionHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits = 0

    def do_GET(self) -> None:
        type(self).hits += 1
        body = json.dumps(
            {
                "counter": type(self).hits,
                "ready": True,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _loopback_transition_server() -> Iterator[tuple[str, int]]:
    _TransitionHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TransitionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_numeric_transition_uses_exactly_requested_get_count(
    tmp_path: Path,
) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _transition_permissions())

    with _loopback_transition_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_NUMERIC_TRANSITION_CONTRACT,
            statement="The local counter strictly increases across three observations.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_numeric_transition_clauses=(_clause(),),
            repeat_observation_count=3,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _TransitionHandler.hits

    assert hits == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["transition_supported_count"] == 2
    assert claim_result["all_transitions_match"] is True
    assert "numeric_transition_read_requires_separate_grant" in (
        result.receipt.limitations
    )
    assert "numeric_transition_contract_enforces_no_time_interval" in (
        result.receipt.limitations
    )
