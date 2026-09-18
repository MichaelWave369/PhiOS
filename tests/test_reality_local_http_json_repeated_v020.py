import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from phios.mandala import MandalaStatus
from phios.reality import (
    JsonMixedContractClause,
    LocalHttpObservation,
    LocalHttpObservationError,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    StdlibLoopbackHttpStateProvider,
)
from phios.spine.runtime import PhiOSSpine


class SequenceHttpProvider:
    name = "sequence-http"

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
    *,
    body: bytes | None = None,
    ready: bool = True,
    queue_depth: int = 3,
    status: int = 200,
    truncated: bool = False,
) -> LocalHttpObservation:
    if body is None:
        body = json.dumps(
            {
                "models": [{"name": "alpha"}],
                "ready": ready,
                "queue_depth": queue_depth,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    return LocalHttpObservation(
        url="http://127.0.0.1:11434/api/state",
        method="GET",
        status_code=status,
        reason="OK",
        headers={"content-type": "application/json"},
        body_sha256=f"{index + 1:064x}",
        body_bytes_observed=len(body),
        body_truncated=truncated,
        body_digest_scope="prefix" if truncated else "full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=2.0 + index,
        provider="sequence-http",
        provider_version="1.0",
        captured_at_utc=f"2026-09-18T22:10:0{index}+00:00",
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
            pointer="/ready",
            scalar_predicate="boolean_is_true",
        ),
        JsonMixedContractClause(
            pointer="/queue_depth",
            scalar_predicate="integer_lte",
            scalar_operand="10",
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
    )


def _claim(
    *,
    count: int | None = 3,
    clauses: tuple[JsonMixedContractClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
        statement="The same bounded contract matches repeated local observations.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=(
            clauses if clauses is not None else _mixed_clauses()
        ),
        repeat_observation_count=count,
    )


def _permissions_without_repeat() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
    ]


def _repeat_permissions() -> list[str]:
    return _permissions_without_repeat() + [
        "reality.local_http.repeat.read",
    ]


def _value_permissions() -> list[str]:
    return _repeat_permissions() + [
        "reality.local_http.semantic.value.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="repeated-mixed-v020",
    )


def test_repeated_contract_requires_two_to_five_observations() -> None:
    assert (
        "local_http_json_repeated_mixed_contract_requires_2_to_5_observations"
        in _claim(count=1).validation_errors()
    )
    assert (
        "local_http_json_repeated_mixed_contract_requires_2_to_5_observations"
        in _claim(count=6).validation_errors()
    )
    assert (
        "local_http_json_repeated_mixed_contract_requires_2_to_5_observations"
        in _claim(count=None).validation_errors()
    )

    bool_count = _claim(count=True)  # type: ignore[arg-type]
    assert (
        "local_http_json_repeated_mixed_contract_requires_2_to_5_observations"
        in bool_count.validation_errors()
    )
    assert _claim(count=2).validation_errors() == ()
    assert _claim(count=5).validation_errors() == ()


def test_repeated_contract_requires_one_to_eight_clauses() -> None:
    empty = _claim(clauses=())
    nine = _claim(
        clauses=tuple(
            JsonMixedContractClause(
                pointer=f"/field{index}",
                expected_json_type="string",
            )
            for index in range(9)
        )
    )

    assert (
        "local_http_json_repeated_mixed_contract_requires_1_to_8_clauses"
        in empty.validation_errors()
    )
    assert (
        "local_http_json_repeated_mixed_contract_requires_1_to_8_clauses"
        in nine.validation_errors()
    )


def test_repeat_count_is_rejected_on_non_repeated_claim() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
        statement="One same-snapshot mixed contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=_mixed_clauses(),
        repeat_observation_count=3,
    )

    assert "repeat_observation_count_only_for_repeated_mixed_contract" in (
        claim.validation_errors()
    )


def test_repeated_contract_rejects_legacy_single_fields() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
        statement="Ambiguous repeated contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_pointer="/ready",
        json_mixed_contract_clauses=_mixed_clauses(),
        repeat_observation_count=3,
    )

    assert (
        "local_http_json_repeated_mixed_contract_disallows_legacy_fields"
        in claim.validation_errors()
    )


def test_repeat_read_grant_is_required_before_any_io(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [_observation(0), _observation(1), _observation(2)]
    )
    spine = _spine(tmp_path, _permissions_without_repeat())

    result = spine.verify_reality(
        claims=(_claim(clauses=_structural_only_clauses()),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.repeat.read"
    )


def test_scalar_repeated_contract_requires_value_grant_before_io(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [_observation(0), _observation(1), _observation(2)]
    )
    spine = _spine(tmp_path, _repeat_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )


def test_structural_only_repeated_contract_needs_no_value_grant(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [_observation(0), _observation(1), _observation(2)]
    )
    spine = _spine(tmp_path, _repeat_permissions())

    result = spine.verify_reality(
        claims=(_claim(clauses=_structural_only_clauses()),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["requires_value_read"] is False
    assert claim_result["supported_count"] == 3
    assert claim_result["all_observations_match"] is True


def test_all_repeated_observations_match_and_keep_distinct_receipts(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [_observation(0), _observation(1), _observation(2)]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["reason"] == (
        "local_http_json_repeated_mixed_all_observations_match"
    )
    assert claim_result["observation_count_requested"] == 3
    assert claim_result["observation_attempts_completed"] == 3
    assert claim_result["supported_count"] == 3
    assert claim_result["contradicted_count"] == 0
    assert claim_result["unresolved_count"] == 0
    assert claim_result["minimum_interval_seconds"] is None
    assert len(claim_result["sample_evidence_refs"]) == 3
    assert len(set(claim_result["sample_evidence_refs"])) == 3
    assert claim_result["series_evidence_ref"] in result.receipt.evidence_used

    timestamps = [
        sample["captured_at_utc"]
        for sample in claim_result["sample_results"]
    ]
    digests = [
        sample["body_sha256"]
        for sample in claim_result["sample_results"]
    ]
    assert timestamps == [
        "2026-09-18T22:10:00+00:00",
        "2026-09-18T22:10:01+00:00",
        "2026-09-18T22:10:02+00:00",
    ]
    assert len(set(digests)) == 3


def test_contradiction_does_not_stop_remaining_observations(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0),
            _observation(1, ready=False),
            _observation(2),
        ]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.CONTRADICTED.value
    assert claim_result["reason"] == (
        "local_http_json_repeated_mixed_sample_contradiction"
    )
    assert claim_result["supported_count"] == 2
    assert claim_result["contradicted_count"] == 1
    assert claim_result["unresolved_count"] == 0
    assert claim_result["all_observations_match"] is False
    assert [sample["verdict"] for sample in claim_result["sample_results"]] == [
        RealityVerdict.SUPPORTED.value,
        RealityVerdict.CONTRADICTED.value,
        RealityVerdict.SUPPORTED.value,
    ]


def test_unresolved_sample_does_not_stop_remaining_observations(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0),
            LocalHttpObservationError("local_http_timeout", "timed out"),
            _observation(2),
        ]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.UNKNOWN
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.UNRESOLVED.value
    assert claim_result["reason"] == (
        "local_http_json_repeated_mixed_sample_unresolved"
    )
    assert claim_result["supported_count"] == 2
    assert claim_result["contradicted_count"] == 0
    assert claim_result["unresolved_count"] == 1
    assert claim_result["sample_results"][1]["reason"] == "local_http_timeout"
    assert claim_result["sample_results"][1]["observation_evidence_ref"] is None


def test_contradiction_precedes_unresolved_in_aggregate(tmp_path: Path) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0, ready=False),
            LocalHttpObservationError("local_http_timeout", "timed out"),
            _observation(2),
        ]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.CONTRADICTED.value
    assert claim_result["contradicted_count"] == 1
    assert claim_result["unresolved_count"] == 1


def test_repeated_scalar_values_do_not_persist_in_sample_or_series_evidence(
    tmp_path: Path,
) -> None:
    secrets = [918273641, 918273642, 918273643]
    observations = [
        _observation(
            index,
            body=json.dumps(
                {
                    "models": [{"name": "alpha"}],
                    "ready": True,
                    "queue_depth": secret,
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        for index, secret in enumerate(secrets)
    ]
    provider = SequenceHttpProvider(observations)
    spine = _spine(tmp_path, _value_permissions())
    clauses = (
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_eq",
            structural_bound=1,
        ),
        JsonMixedContractClause(
            pointer="/queue_depth",
            scalar_predicate="integer_gte",
            scalar_operand="1",
        ),
    )

    result = spine.verify_reality(
        claims=(_claim(clauses=clauses),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]

    refs = list(claim_result["sample_evidence_refs"]) + [
        claim_result["series_evidence_ref"]
    ]
    for evidence_ref in refs:
        evidence_bytes = spine.soma.evidence.read_bytes(evidence_ref)
        serialized = evidence_bytes.decode("utf-8")
        assert "observed_value" not in serialized
        for secret in secrets:
            assert str(secret) not in serialized

    first_sample = json.loads(
        spine.soma.evidence.read_bytes(claim_result["sample_evidence_refs"][0])
    )
    assert "body" not in first_sample["http_observation"]
    scalar_result = first_sample["semantic_observation"]["clause_results"][1]
    assert scalar_result["mode"] == "scalar"
    assert scalar_result["predicate_matches"] is True
    assert scalar_result["measurement"] is None


def test_status_mismatch_is_one_contradicted_sample_not_early_stop(
    tmp_path: Path,
) -> None:
    provider = SequenceHttpProvider(
        [
            _observation(0),
            _observation(1, status=503),
            _observation(2),
        ]
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    claim_result = result.claim_results[0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    assert claim_result["contradicted_count"] == 1
    assert claim_result["sample_results"][1]["clauses_evaluated"] == 0
    assert claim_result["sample_results"][1]["reason"] == (
        "local_http_json_repeated_mixed_sample_status_mismatch"
    )


class _RepeatedHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits = 0

    def do_GET(self) -> None:
        type(self).hits += 1
        body = json.dumps(
            {
                "models": [{"name": "alpha"}],
                "ready": True,
                "queue_depth": type(self).hits,
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
def _loopback_repeated_server() -> Iterator[tuple[str, int]]:
    _RepeatedHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RepeatedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_repeated_contract_uses_exactly_requested_get_count(
    tmp_path: Path,
) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _value_permissions())
    clauses = (
        JsonMixedContractClause(
            pointer="/models",
            structural_predicate="array_length_gte",
            structural_bound=1,
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
    )

    with _loopback_repeated_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
            statement="Three bounded local observations satisfy the same contract.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_mixed_contract_clauses=clauses,
            repeat_observation_count=3,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _RepeatedHandler.hits

    assert hits == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["supported_count"] == 3
    assert claim_result["minimum_interval_seconds"] is None
    assert "repeated_http_read_requires_separate_grant" in (
        result.receipt.limitations
    )
    assert "repeated_mixed_success_is_not_continuous_health" in (
        result.receipt.limitations
    )
