from __future__ import annotations

from pathlib import Path

from phios.mandala import MandalaStatus
from phios.reality import (
    InterfaceObservation,
    ObservationFrontierBuilder,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    TcpListenerObservation,
)
from phios.spine.runtime import PhiOSSpine


class FakeTcpProvider:
    name = "fake-frontier-tcp"

    def __init__(self, *, listening: bool) -> None:
        self.listening = listening
        self.calls: list[tuple[int, str | None]] = []

    def observe(
        self,
        *,
        local_port: int,
        local_address: str | None = None,
    ) -> TcpListenerObservation:
        self.calls.append((local_port, local_address))
        return TcpListenerObservation(
            local_port=local_port,
            local_address_filter=local_address,
            is_listening=self.listening,
            matched_local_addresses=(
                ("127.0.0.1",) if self.listening else ()
            ),
            provider=self.name,
            provider_version="1.0",
            captured_at_utc="2026-09-21T17:00:00+00:00",
        )


class FakeInterfaceProvider:
    name = "fake-frontier-interface"

    def __init__(self, observation: InterfaceObservation | None) -> None:
        self.observation = observation

    def observe(self, interface_name: str) -> InterfaceObservation | None:
        return self.observation


def _tcp_claim(*, expected: bool) -> RealityClaim:
    return RealityClaim(
        claim_id="tcp-claim",
        kind=RealityClaimKind.LOCAL_TCP_LISTENER_STATE,
        statement="Port 8123 is not listening." if not expected else "Port 8123 is listening.",
        local_port=8123,
        expected_listening=expected,
    )


def _world_claim() -> RealityClaim:
    return RealityClaim(
        claim_id="world-claim",
        kind=RealityClaimKind.WORLD_STATE,
        statement="No external side effect occurred anywhere.",
    )


def test_supported_negative_tcp_state_is_bounded_to_exact_frontier(
    tmp_path: Path,
) -> None:
    provider = FakeTcpProvider(listening=False)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify", "reality.local_socket.read"),
        task_id="frontier-negative",
    )

    result = spine.verify_reality(
        claims=(_tcp_claim(expected=False),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.SUPPORTED.value
    assert result.observability is not None
    assert result.observability.status == "BOUNDED"
    assert result.observability.bounded_negative_state_claim_ids == ("tcp-claim",)
    assert result.observability.unbounded_negative_state_claim_ids == ()
    coverage = result.claim_results[0]["observation_coverage"]
    assert coverage["surface"] == "local_tcp_listener_state"
    assert coverage["coverage_kind"] == "exact_point"
    assert coverage["status"] == "COVERED"
    assert coverage["bounded_negative_state_support"] is True
    assert result.claim_results[0]["negative_state_support_scope"] == (
        "supported_only_within_observation_frontier"
    )


def test_generic_world_negative_claim_remains_outside_frontier(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="frontier-world",
    )

    result = spine.verify_reality(claims=(_world_claim(),))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.observability is not None
    assert result.observability.status == "OUTSIDE_FRONTIER"
    coverage = result.claim_results[0]["observation_coverage"]
    assert coverage["status"] == "UNOBSERVED"
    assert coverage["surface"] == "world_state"
    assert "independent_world_verifier_not_installed" in coverage["limitations"]


def test_mixed_bounded_and_unobserved_claims_are_partial(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify", "reality.local_socket.read"),
        task_id="frontier-mixed",
    )

    result = spine.verify_reality(
        claims=(_tcp_claim(expected=False), _world_claim()),
        tcp_listener_provider=FakeTcpProvider(listening=False),
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.observability is not None
    assert result.observability.status == "PARTIAL"
    assert result.observability.covered_claim_ids == ("tcp-claim",)
    assert result.observability.unobserved_claim_ids == ("world-claim",)


def test_observability_hashes_are_bound_into_reality_receipt(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify", "reality.local_socket.read"),
        task_id="frontier-binding",
    )

    result = spine.verify_reality(
        claims=(_tcp_claim(expected=True),),
        tcp_listener_provider=FakeTcpProvider(listening=True),
    )

    assert result.observability is not None
    assert result.receipt.observation_frontier_sha256 == (
        result.observability.observation_frontier_sha256
    )
    assert result.receipt.observability_receipt_sha256 == (
        result.observability.receipt_sha256
    )
    assert result.receipt.observability_status == "BOUNDED"
    assert result.observability.operational_authority is False
    assert result.observability.action_authority is False
    assert result.observability.execution_authority is False


def test_observation_frontier_does_not_insert_a_second_mandala_authority_plane(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify", "reality.local_socket.read"),
        task_id="frontier-inline",
    )

    spine.verify_reality(
        claims=(_tcp_claim(expected=False),),
        tcp_listener_provider=FakeTcpProvider(listening=False),
    )

    receipts = spine.mandala_ledger.recent(2)
    assert [item["receipt_type"] for item in receipts] == [
        "GateReceipt",
        "RealityReceipt",
    ]


def test_missing_specific_observation_grant_is_outside_frontier(
    tmp_path: Path,
) -> None:
    provider = FakeTcpProvider(listening=False)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="frontier-no-specific-grant",
    )

    result = spine.verify_reality(
        claims=(_tcp_claim(expected=False),),
        tcp_listener_provider=provider,
    )

    assert provider.calls == []
    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.observability is not None
    assert result.observability.status == "OUTSIDE_FRONTIER"
    assert result.observability.bounded_negative_state_claim_ids == ()
    assert result.observability.unbounded_negative_state_claim_ids == ("tcp-claim",)


def test_interface_not_found_is_partial_without_persisted_absence_evidence(
    tmp_path: Path,
) -> None:
    provider = FakeInterfaceProvider(None)
    claim = RealityClaim(
        claim_id="iface-claim",
        kind=RealityClaimKind.LOCAL_INTERFACE_STATE,
        statement="NoSuchInterface is down.",
        interface_name="NoSuchInterface",
        expected_is_up=False,
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify", "reality.local_interface.read"),
        task_id="frontier-interface-missing",
    )

    result = spine.verify_reality(
        claims=(claim,),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.observability is not None
    assert result.observability.status == "PARTIAL"
    coverage = result.claim_results[0]["observation_coverage"]
    assert coverage["status"] == "PARTIAL"
    assert coverage["bounded_negative_state_support"] is False
    assert (
        "provider_lookup_completed_without_persisted_absence_observation"
        in coverage["limitations"]
    )


def test_frontier_hash_is_deterministic_for_same_claim_and_observation() -> None:
    builder = ObservationFrontierBuilder()
    claim = _tcp_claim(expected=False)
    result = {
        "claim_id": claim.claim_id,
        "kind": claim.kind.value,
        "statement": claim.statement,
        "verdict": RealityVerdict.SUPPORTED.value,
        "reason": "direct_local_tcp_observation_matches_expected_state",
        "scope": "local_tcp_listener_state",
        "observed_listening": False,
        "provider": "test-provider",
        "provider_version": "1",
        "observation_evidence_ref": "sha256:" + ("a" * 64),
    }

    first = builder.build(
        claims=(claim,),
        results=(result,),
        interface_provider=None,
        tcp_listener_provider=None,
        local_http_provider=None,
    )
    second = builder.build(
        claims=(claim,),
        results=(dict(result),),
        interface_provider=None,
        tcp_listener_provider=None,
        local_http_provider=None,
    )

    assert first.frontier_sha256 == second.frontier_sha256
    assert first.to_dict() == second.to_dict()



def test_source_text_absence_is_bounded_to_readable_cited_set(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="frontier-source",
    )
    evidence_ref = spine.soma.evidence.put_text(
        "alpha beta gamma"
    ).evidence_ref
    claim = RealityClaim(
        claim_id="source-claim",
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text contains delta.",
        evidence_refs=(evidence_ref,),
        expected_text="delta",
    )

    result = spine.verify_reality(claims=(claim,))

    assert result.claim_results[0]["verdict"] == RealityVerdict.CONTRADICTED.value
    assert result.observability is not None
    assert result.observability.status == "BOUNDED"
    coverage = result.claim_results[0]["observation_coverage"]
    assert coverage["status"] == "COVERED"
    assert coverage["coverage_kind"] == "bounded_set"
    assert coverage["evidence_refs"] == [evidence_ref]
    assert coverage["explicit_negative_state_claim"] is False
    assert "cited_readable_text_evidence_only" in coverage["limitations"]


def test_complete_discrete_http_series_is_covered_but_not_continuous() -> None:
    builder = ObservationFrontierBuilder()
    claim = RealityClaim(
        claim_id="series-claim",
        kind=RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
        statement="Two bounded observations match.",
        http_url="http://127.0.0.1:8080/status",
        expected_http_status=200,
        repeat_observation_count=2,
    )
    result = {
        "claim_id": claim.claim_id,
        "kind": claim.kind.value,
        "statement": claim.statement,
        "verdict": RealityVerdict.SUPPORTED.value,
        "reason": "local_http_json_repeated_mixed_all_observations_match",
        "scope": "local_http_json_repeated_mixed_contract",
        "observation_count_requested": 2,
        "unresolved_count": 0,
        "sample_results": [
            {
                "sample_index": 0,
                "verdict": RealityVerdict.SUPPORTED.value,
                "provider": "series-provider",
                "provider_version": "1",
                "observation_evidence_ref": "sha256:" + ("a" * 64),
            },
            {
                "sample_index": 1,
                "verdict": RealityVerdict.SUPPORTED.value,
                "provider": "series-provider",
                "provider_version": "1",
                "observation_evidence_ref": "sha256:" + ("b" * 64),
            },
        ],
        "series_evidence_ref": "sha256:" + ("c" * 64),
    }

    frontier = builder.build(
        claims=(claim,),
        results=(result,),
        interface_provider=None,
        tcp_listener_provider=None,
        local_http_provider=None,
    )

    entry = frontier.entries[0]
    assert entry.status == "COVERED"
    assert entry.coverage_kind == "bounded_series"
    assert "series_is_not_continuous_monitoring" in entry.limitations


def test_truncated_semantic_http_observation_is_partial() -> None:
    builder = ObservationFrontierBuilder()
    claim = RealityClaim(
        claim_id="http-semantic",
        kind=RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
        statement="Status body has an object.",
        http_url="http://127.0.0.1:8080/status",
        expected_http_status=200,
        json_pointer="",
        expected_json_type="object",
    )
    result = {
        "claim_id": claim.claim_id,
        "kind": claim.kind.value,
        "statement": claim.statement,
        "verdict": RealityVerdict.UNRESOLVED.value,
        "reason": "local_http_json_contract_body_truncated",
        "scope": "local_http_json_contract",
        "provider": "http-provider",
        "provider_version": "1",
        "body_truncated": True,
        "observation_evidence_ref": "sha256:" + ("d" * 64),
    }

    frontier = builder.build(
        claims=(claim,),
        results=(result,),
        interface_provider=None,
        tcp_listener_provider=None,
        local_http_provider=None,
    )

    assert frontier.status == "PARTIAL"
    entry = frontier.entries[0]
    assert entry.status == "PARTIAL"
    assert "http_response_observed_but_semantic_body_truncated" in entry.limitations
