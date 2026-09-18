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


class CadencedSequenceProvider:
    name = "cadenced-sequence-http"

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
        body_sha256=f"{index + 21:064x}",
        body_bytes_observed=len(body),
        body_truncated=False,
        body_digest_scope="full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=2.0 + index,
        provider="cadenced-sequence-http",
        provider_version="1.0",
        captured_at_utc=(
            captured_at_utc
            if captured_at_utc is not None
            else f"2026-09-18T22:40:0{index}+00:00"
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
    minimum: float | None = 2.0,
    maximum: float | None = 3.0,
    clauses: tuple[JsonMixedContractClause, ...] | None = None,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
        statement="The observations satisfy one bounded cadence-window contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=(
            clauses if clauses is not None else _mixed_clauses()
        ),
        repeat_observation_count=count,
        minimum_interval_seconds=minimum,
        maximum_interval_seconds=maximum,
    )


def _base_permissions() -> list[str]:
    return [
        "reality.verify",
        "reality.local_http.read",
        "reality.local_http.semantic.read",
        "reality.local_http.repeat.read",
        "reality.local_http.timing.wait",
    ]


def _cadence_permissions() -> list[str]:
    return _base_permissions() + [
        "reality.local_http.timing.cadence",
    ]


def _value_permissions() -> list[str]:
    return _cadence_permissions() + [
        "reality.local_http.semantic.value.read",
    ]


def _spine(tmp_path: Path, permissions: list[str]) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=permissions,
        task_id="cadenced-mixed-v022",
    )


def _patch_clock(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> None:
    monkeypatch.setattr(reality_service, "monotonic", clock.monotonic)
    monkeypatch.setattr(reality_service, "sleep", clock.sleep)


def test_cadenced_contract_requires_two_to_five_observations() -> None:
    assert (
        "local_http_json_cadenced_mixed_contract_requires_2_to_5_observations"
        in _claim(count=1).validation_errors()
    )
    assert (
        "local_http_json_cadenced_mixed_contract_requires_2_to_5_observations"
        in _claim(count=6).validation_errors()
    )
    assert _claim(count=2).validation_errors() == ()
    assert _claim(count=5).validation_errors() == ()


def test_cadenced_contract_requires_one_to_eight_clauses() -> None:
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
        "local_http_json_cadenced_mixed_contract_requires_1_to_8_clauses"
        in empty.validation_errors()
    )
    assert (
        "local_http_json_cadenced_mixed_contract_requires_1_to_8_clauses"
        in nine.validation_errors()
    )


def test_cadence_window_is_bounded_and_ordered() -> None:
    min_error = (
        "local_http_json_cadenced_mixed_contract_requires_min_interval_0_05_to_10_seconds"
    )
    max_error = (
        "local_http_json_cadenced_mixed_contract_requires_max_interval_0_05_to_10_seconds"
    )
    order_error = (
        "local_http_json_cadenced_mixed_contract_requires_max_interval_gte_min"
    )

    assert min_error in _claim(minimum=None).validation_errors()
    assert min_error in _claim(minimum=0.049).validation_errors()
    assert max_error in _claim(maximum=None).validation_errors()
    assert max_error in _claim(maximum=10.001).validation_errors()
    assert order_error in _claim(minimum=2.0, maximum=1.0).validation_errors()
    assert _claim(minimum=0.05, maximum=0.05).validation_errors() == ()
    assert _claim(minimum=1.0, maximum=10.0).validation_errors() == ()


def test_maximum_interval_is_rejected_on_v021_timed_claim() -> None:
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
        statement="Minimum-only timed contract.",
        http_url="http://127.0.0.1:11434/api/state",
        expected_http_status=200,
        json_mixed_contract_clauses=_mixed_clauses(),
        repeat_observation_count=3,
        minimum_interval_seconds=1.0,
        maximum_interval_seconds=2.0,
    )

    assert "maximum_interval_seconds_only_for_cadenced_mixed_contract" in (
        claim.validation_errors()
    )


def test_cadence_grant_is_required_before_io(tmp_path: Path) -> None:
    provider = CadencedSequenceProvider(
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
        "missing_grant:reality.local_http.timing.cadence"
    )


def test_scalar_cadence_contract_requires_value_grant_before_io(
    tmp_path: Path,
) -> None:
    provider = CadencedSequenceProvider(
        clock=None,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _cadence_permissions())

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert provider.calls == 0
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["reason"] == (
        "missing_grant:reality.local_http.semantic.value.read"
    )


def test_structural_cadence_contract_needs_no_value_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
    )
    spine = _spine(tmp_path, _cadence_permissions())

    result = spine.verify_reality(
        claims=(
            _claim(
                minimum=1.0,
                maximum=2.0,
                clauses=_structural_clauses(),
            ),
        ),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["requires_value_read"] is False


def test_cadence_window_passes_when_starts_are_inside_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
        durations=[0.5, 2.5, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(minimum=2.0, maximum=3.0),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert provider.start_times == [0.0, 2.0, 4.5]
    assert clock.sleeps == [1.5]
    assert result.receipt.status is MandalaStatus.ACCEPTED

    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["minimum_observed_interval_seconds"] == 2.0
    assert claim_result["maximum_observed_interval_seconds"] == 2.5
    assert [
        sample["elapsed_since_previous_start_seconds"]
        for sample in claim_result["sample_results"]
    ] == [None, 2.0, 2.5]
    assert [
        sample["cadence_satisfied"]
        for sample in claim_result["sample_results"]
    ] == [None, True, True]


def test_provider_overrun_violates_upper_bound_but_does_not_stop_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[_observation(0), _observation(1), _observation(2)],
        durations=[0.5, 4.0, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(minimum=2.0, maximum=3.0),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert provider.start_times == [0.0, 2.0, 6.0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.CONTRADICTED.value
    assert claim_result["reason"] == (
        "local_http_json_cadenced_mixed_window_violation"
    )
    assert claim_result["cadence_satisfied"] is False
    assert claim_result["supported_count"] == 3
    assert claim_result["contradicted_count"] == 0
    assert claim_result["maximum_observed_interval_seconds"] == 4.0
    assert claim_result["sample_results"][2]["upper_bound_satisfied"] is False


def test_semantic_contradiction_still_evaluates_all_in_window_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[
            _observation(0),
            _observation(1, ready=False),
            _observation(2),
        ],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(minimum=1.0, maximum=2.0),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert provider.start_times == [0.0, 1.0, 2.0]
    assert result.receipt.status is MandalaStatus.DISPUTED
    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["contradicted_count"] == 1
    assert claim_result["reason"] == (
        "local_http_json_cadenced_mixed_sample_contradiction"
    )


def test_timeout_keeps_cadence_measurement_and_series_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[
            _observation(0),
            LocalHttpObservationError("local_http_timeout", "timed out"),
            _observation(2),
        ],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(minimum=0.5, maximum=1.0),),
        local_http_provider=provider,
    )

    assert provider.calls == 3
    assert provider.start_times == [0.0, 0.5, 1.0]
    assert result.receipt.status is MandalaStatus.UNKNOWN
    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["unresolved_count"] == 1
    assert claim_result["sample_results"][1]["cadence_satisfied"] is True
    assert claim_result["sample_results"][1]["observation_evidence_ref"] is None


def test_wall_clock_timestamps_do_not_establish_cadence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    same_wall_clock = "2026-09-18T22:50:00+00:00"
    provider = CadencedSequenceProvider(
        clock=clock,
        items=[
            _observation(0, captured_at_utc=same_wall_clock),
            _observation(1, captured_at_utc=same_wall_clock),
            _observation(2, captured_at_utc=same_wall_clock),
        ],
        durations=[0.25, 0.25, 0.0],
    )
    spine = _spine(tmp_path, _value_permissions())

    result = spine.verify_reality(
        claims=(_claim(minimum=1.0, maximum=1.5),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert {
        sample["captured_at_utc"]
        for sample in claim_result["sample_results"]
    } == {same_wall_clock}


def test_cadenced_scalar_values_do_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    _patch_clock(monkeypatch, clock)
    secrets = [671234561, 671234562, 671234563]
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
    provider = CadencedSequenceProvider(clock=clock, items=items)
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
        claims=(
            _claim(
                minimum=0.5,
                maximum=1.0,
                clauses=clauses,
            ),
        ),
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


class _CadenceHandler(BaseHTTPRequestHandler):
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
def _loopback_cadence_server() -> Iterator[tuple[str, int]]:
    _CadenceHandler.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CadenceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_live_cadence_contract_uses_requested_count_and_window(
    tmp_path: Path,
) -> None:
    provider = StdlibLoopbackHttpStateProvider()
    spine = _spine(tmp_path, _value_permissions())

    with _loopback_cadence_server() as (host, port):
        claim = RealityClaim.create(
            kind=RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
            statement="Three local observations stay inside the cadence window.",
            http_url=f"http://{host}:{port}/api/state",
            expected_http_status=200,
            json_mixed_contract_clauses=_mixed_clauses(),
            repeat_observation_count=3,
            minimum_interval_seconds=0.05,
            maximum_interval_seconds=2.0,
        )
        result = spine.verify_reality(
            claims=(claim,),
            local_http_provider=provider,
        )
        hits = _CadenceHandler.hits

    assert hits == 3
    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["cadence_satisfied"] is True
    assert claim_result["minimum_observed_interval_seconds"] >= 0.05
    assert claim_result["maximum_observed_interval_seconds"] <= 2.0
    assert "cadenced_http_control_requires_separate_grant" in (
        result.receipt.limitations
    )
    assert "cadenced_mixed_window_is_not_continuous_monitoring" in (
        result.receipt.limitations
    )
