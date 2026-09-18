import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

import phios.reality.service as reality_service
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class EnvelopeSequenceProvider:
    name = "temporal-envelope-sequence-http"

    def __init__(
        self,
        *,
        clock: FakeClock | None,
        items: list[LocalHttpObservation | Exception],
        durations: list[float] | None = None,
    ) -> None:
        self.clock = clock
        self.items = list(items)
        self.durations = durations or [0.0] * len(items)
        self.calls = 0
        self.start_times: list[float] = []

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        index = self.calls
        self.calls += 1
        if self.clock is not None:
            self.start_times.append(self.clock.monotonic())
        item = self.items[index]
        if self.clock is not None:
            self.clock.advance(self.durations[index])
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
    captured_at_utc: str | None = None,
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
        body_sha256=f"{index + 31:064x}",
        body_bytes_observed=len(body),
        body_truncated=False,
        body_digest_scope="full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=2.0 + index,
        provider="temporal-envelope-sequence-http",
        provider_version="1.0",
        captured_at_utc=(
            captured_at_utc
            if captured_at_utc is not None
            else f"2026-09-18T23:00:0{index}+00:00"
        ),
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


def _structural_clauses() -> tuple[JsonMixedContractClause, ...]:
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
    minimum_interval: float | None = 1.0,
    maximum_interval: float | None = 2.0,
    minimum_span: float | None = 2.0,
    maximum_span: float | None = 4.0,
    clauses: tuple[JsonMixedContractClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_TEMPORAL_ENVELOPE_MIXED_CONTRACT,
        statement="The observations satisfy one bounded temporal envelope.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=(
            clauses if clauses is not None else _mixed_clauses()
        ),
        repeat_observation_count=count,
        minimum_interval_seconds=minimum_interval,
        maximum_interval_seconds=maximum_interval,
        minimum_series_span_seconds=minimum_span,
        maximum_series_span_seconds=maximum_span,
    )


def _base_permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
        "reality.local_http.repeat.read",
        "reality.local_http.timing.wait",
        "reality.local_http.timing.cadence",
    ]


def _envelope_permissions() -> list[str]:
    return _base_permissions() + [
        "reality.local_http.timing.envelope",
    ]


def _value_permissions() -> list[str]:
    return _envelope_permissions() + [
        "reality.local_http.semantic.value.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="temporal-envelope-v023",
    )


def _patch_clock(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> None:
    monkeypatch.setattr(reality_service, "monotonic", clock.monotonic)
    monkeypatch.setattr(reality_service, "sleep", clock.sleep)


def test_temporal_envelope_requires_two_to_five_observations() -> None:
    error = (
        "local_http_json_temporal_envelope_contract_requires_2_to_5_observations"
    )
    assert error in _claim(count=1).validation_errors()
    assert error in _claim(count=6).validation_errors()
    assert error in _claim(count=None).validation_errors()
    assert _claim(count=2).validation_errors() == ()
    assert _claim(count=5).validation_errors() == ()


def test_temporal_envelope_requires_one_to_eight_clauses() -> None:
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

    error = "local_http_json_temporal_envelope_contract_requires_1_to_8_clauses"
    assert error in empty.validation_errors()
    assert error in nine.validation_errors()


def test_temporal_envelope_interval_and_span_bounds() -> None:
    min_interval_error = (
        "local_http_json_temporal_envelope_contract_requires_min_interval_0_05_to_10_seconds"
    )
    max_interval_error = (
        "local_http_json_temporal_envelope_contract_requires_max_interval_0_05_to_10_seconds"
    )
    interval_order_error = (
        "local_http_json_temporal_envelope_contract_requires_max_interval_gte_min"
    )
    min_span_error = (
        "local_http_json_temporal_envelope_contract_requires_min_span_0_05_to_40_seconds"
    )
    max_span_error = (
        "local_http_json_temporal_envelope_contract_requires_max_span_0_05_to_40_seconds"
    )
    span_order_error = (
        "local_http_json_temporal_envelope_contract_requires_max_span_gte_min"
    )

    assert min_interval_error in _claim(minimum_interval=None).validation_errors()
    assert min_interval_error in _claim(minimum_interval=0.049).validation_errors()
    assert max_interval_error in _claim(maximum_interval=None).validation_errors()
    assert max_interval_error in _claim(maximum_interval=10.001).validation_errors()
    assert interval_order_error in _claim(
        minimum_interval=2.0,
        maximum_interval=1.0,
    ).validation_errors()

    assert min_span_error in _claim(minimum_span=None).validation_errors()
    assert min_span_error in _claim(minimum_span=0.049).validation_errors()
    assert max_span_error in _claim(maximum_span=None).validation_errors()
    assert max_span_error in _claim(maximum_span=40.001).validation_errors()
    assert span_order_error in _claim(
        minimum_span=4.0,
        maximum_span=3.0,
    ).validation_errors()


def test_temporal_envelope_rejects_mathematically_infeasible_span() -> None:
    claim = _claim(
        count=3,
        minimum_interval=1.0,
        maximum_interval=2.0,
        minimum_span=5.0,
        maximum_span=6.0,
    )

    assert "local_http_json_temporal_envelope_contract_infeasible_span" in (
        claim.validation_errors()
    )


def test_infeasible_temporal_envelope_blocks_before_io(tmp_path: Path) -> None:
    provider = EnvelopeSequenceProvider(
        clock=None,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _value_permissions())
    claim = _claim(
        count=3,
        minimum_interval=1.0,
        maximum_interval=2.0,
        minimum_span=5.0,
        maximum_span=6.0,
    )

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert "local_http_json_temporal_envelope_contract_infeasible_span" in (
        result.claim_results[0]["reason"]
    )


def test_series_span_fields_are_rejected_on_v022_claim() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
        statement="Cadence only.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=_mixed_clauses(),
        repeat_observation_count=3,
        minimum_interval_seconds=1.0,
        maximum_interval_seconds=2.0,
        minimum_series_span_seconds=2.0,
        maximum_series_span_seconds=4.0,
    )

    assert "series_span_fields_only_for_temporal_envelope_mixed_contract" in (
        claim.validation_errors()
    )


def test_envelope_grant_is_required_before_io(tmp_path: Path) -> None:
    provider = EnvelopeSequenceProvider(
        clock=None,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _base_permissions())

    result = spine.verify_reality(
        claims=(_claim(clauses=_structural_clauses()),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.timing.envelope"
    )


def test_scalar_envelope_requires_value_grant_before_io(tmp_path: Path) -> None:
    provider = EnvelopeSequenceProvider(
        clock=None,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _envelope_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )


def test_structural_envelope_needs_no_value_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _envelope_permissions())

    result = spine.verify_reality(
        claims=(_claim(clauses=_structural_clauses()),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["requires_value_read"] is False


def test_scheduler_stretches_series_to_meet_minimum_span(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
        durations=[0.25, 0.25, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                minimum_interval=1.0,
                maximum_interval=2.0,
                minimum_span=3.5,
                maximum_span=4.0,
            ),
        ),
        local_http_provider=provider,
    )

    assert provider.start_times == [0.0, 1.5, 3.5]
    assert clock.sleeps == [1.25, 1.75]
    assert result.receipt.status is MandalaStatus.ACCEPTED

    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["scheduling_path_satisfied"] is True
    assert claim_result["total_series_span_seconds"] == 3.5
    assert claim_result["series_span_satisfied"] is True
    assert claim_result["temporal_envelope_satisfied"] is True

    assert [
        sample["admissible_start_offset_min_seconds"]
        for sample in claim_result["sample_results"]
    ] == [None, 1.5, 3.5]
    assert [
        sample["admissible_start_offset_max_seconds"]
        for sample in claim_result["sample_results"]
    ] == [None, 2.0, 3.5]


def test_whole_series_span_can_fail_while_each_cadence_interval_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
        durations=[3.0, 3.0, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                minimum_interval=1.0,
                maximum_interval=3.0,
                minimum_span=2.0,
                maximum_span=4.0,
            ),
        ),
        local_http_provider=provider,
    )

    assert provider.start_times == [0.0, 3.0, 6.0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]

    assert claim_result["supported_count"] == 3
    assert claim_result["contradicted_count"] == 0
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["total_series_span_seconds"] == 6.0
    assert claim_result["series_span_satisfied"] is False
    assert claim_result["temporal_envelope_satisfied"] is False
    assert claim_result["reason"] == (
        "local_http_json_temporal_envelope_series_span_violation"
    )
    assert claim_result["sample_results"][2]["start_window_satisfied"] is False


def test_semantic_contradiction_inside_valid_temporal_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[
            _observation(0),
            _observation(1, ready=False),
            _observation(2),
        ],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.start_times == [0.0, 1.0, 2.0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["temporal_envelope_satisfied"] is True
    assert claim_result["contradicted_count"] == 1
    assert claim_result["reason"] == (
        "local_http_json_temporal_envelope_sample_contradiction"
    )


def test_timeout_preserves_timing_and_series_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[
            _observation(0),
            LocalHttpObservationError("local_http_timeout", "timed out"),
            _observation(2),
        ],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.start_times == [0.0, 1.0, 2.0]
    assert result.receipt.status is MandalaStatus.UNKNOWN
    claim_result = result.claim_results[0]
    assert claim_result["temporal_envelope_satisfied"] is True
    assert claim_result["supported_count"] == 2
    assert claim_result["unresolved_count"] == 1
    assert claim_result["sample_results"][1]["observation_evidence_ref"] is None


def test_wall_clock_timestamps_do_not_establish_series_span(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    same_wall_clock = "2026-09-18T23:10:00+00:00"
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[
            _observation(0, captured_at_utc=same_wall_clock),
            _observation(1, captured_at_utc=same_wall_clock),
            _observation(2, captured_at_utc=same_wall_clock),
        ],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["total_series_span_seconds"] == 2.0
    assert {
        sample["captured_at_utc"]
        for sample in claim_result["sample_results"]
    } == {same_wall_clock}


def test_temporal_envelope_scalar_values_do_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    secrets = [561234561, 561234562, 561234563]
    items = [
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
    provider = EnvelopeSequenceProvider(clock=clock, items=items)
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
        serialized = spine.soma.evidence.read_bytes(evidence_ref).decode("utf-8")
        assert "observed_value" not in serialized
        for secret in secrets:
            assert str(secret) not in serialized


def test_series_span_verdict_uses_persisted_nine_decimal_precision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = EnvelopeSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1)],
        durations=[4.0000000004, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                count=2,
                minimum_interval=1.0,
                maximum_interval=5.0,
                minimum_span=1.0,
                maximum_span=4.0,
            ),
        ),
        local_http_provider=provider,
    )

    assert provider.start_times == [0.0, 4.0000000004]
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["total_series_span_seconds"] == 4.0
    assert claim_result["series_span_upper_satisfied"] is True
    assert claim_result["sample_results"][1]["start_window_satisfied"] is True


class _EnvelopeHandler(BaseHTTPRequestHandler):
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
def _loopback_envelope_server() -> Iterator[tuple[str, int]]:
    _EnvelopeHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EnvelopeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_temporal_envelope_uses_requested_count_and_span(
    tmp_path: Path,
) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _value_permissions())

    with _loopback_envelope_server() as (host, port):
        claim = RealityClaim.create(
            kind=(
                RealityClaimKind.LOCAL_HTTP_JSON_TEMPORAL_ENVELOPE_MIXED_CONTRACT
            ),
            statement="Three local observations satisfy the temporal envelope.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_mixed_contract_clauses=_mixed_clauses(),
            repeat_observation_count=3,
            minimum_interval_seconds=0.05,
            maximum_interval_seconds=2.0,
            minimum_series_span_seconds=0.1,
            maximum_series_span_seconds=4.0,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _EnvelopeHandler.hits

    assert hits == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["series_span_satisfied"] is True
    assert claim_result["temporal_envelope_satisfied"] is True
    assert claim_result["total_series_span_seconds"] >= 0.1
    assert claim_result["total_series_span_seconds"] <= 4.0
    assert "temporal_envelope_control_requires_separate_grant" in (
        result.receipt.limitations
    )
    assert "temporal_envelope_is_not_continuous_monitoring" in (
        result.receipt.limitations
    )
