import json
from pathlib import Path

from phios.mandala import MandalaStatus
from phios.reality import (
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    TcpListenerObservation,
    TcpListenerObservationError,
)
from phios.spine.runtime import PhiOSSpine


class FakeTcpProvider:
    name = "fake-tcp"

    def __init__(
        self,
        observation: TcpListenerObservation | None = None,
        *,
        error: TcpListenerObservationError | None = None,
    ) -> None:
        self.observation = observation
        self.error = error
        self.calls: list[tuple[int, str | None]] = []

    def observe(
        self,
        *,
        local_port: int,
        local_address: str | None = None,
    ) -> TcpListenerObservation:
        self.calls.append((local_port, local_address))
        if self.error is not None:
            raise self.error
        assert self.observation is not None
        return self.observation


def _observation(
    *,
    port: int = 8000,
    address: str | None = None,
    listening: bool = True,
) -> TcpListenerObservation:
    return TcpListenerObservation(
        local_port=port,
        local_address_filter=address,
        is_listening=listening,
        matched_local_addresses=("127.0.0.1",) if listening else (),
        provider="fake-tcp",
        provider_version="1.0",
        captured_at_utc="2026-09-18T17:00:00+00:00",
    )


def _claim(
    *,
    port: int = 8000,
    address: str | None = None,
    expected: bool = True,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_TCP_LISTENER_STATE,
        statement=(
            f"Local TCP port {port} is "
            f"{'listening' if expected else 'not listening'}."
        ),
        local_port=port,
        local_address=address,
        expected_listening=expected,
    )


def test_local_tcp_still_requires_reality_verify(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.local_socket.read"],
        task_id="tcp-base-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "missing_grant:reality.verify" in result.receipt.limitations


def test_local_tcp_requires_specific_socket_grant(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="tcp-read-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["verdict"] == RealityVerdict.BLOCKED.value
    assert provider.calls == []
    assert result.claim_results[0]["reason"] == "missing_grant:reality.local_socket.read"


def test_listener_observation_can_support_claim(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation(listening=True))
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-supported",
    )

    result = spine.verify_reality(
        claims=(_claim(expected=True),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["observed_listening"] is True
    assert provider.calls == [(8000, None)]

    evidence_ref = claim_result["observation_evidence_ref"]
    assert evidence_ref in result.receipt.evidence_used
    observation = json.loads(spine.soma.evidence.read_bytes(evidence_ref))
    assert observation["local_port"] == 8000
    assert observation["is_listening"] is True
    assert observation["matched_local_addresses"] == ["127.0.0.1"]


def test_absence_can_support_expected_not_listening(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation(listening=False))
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-absent",
    )

    result = spine.verify_reality(
        claims=(_claim(expected=False),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.SUPPORTED.value
    assert result.claim_results[0]["observed_listening"] is False


def test_conflicting_listener_state_is_disputed(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation(listening=True))
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-conflict",
    )
    claim = _claim(expected=False)

    result = spine.verify_reality(
        claims=(claim,),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.CONTRADICTED.value
    assert result.receipt.unresolved_contradictions == (claim.claim_id,)


def test_socket_provider_failure_is_unresolved(tmp_path: Path) -> None:
    provider = FakeTcpProvider(
        error=TcpListenerObservationError("provider unavailable")
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-provider-failure",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.claim_results[0]["reason"] == "local_tcp_observation_unavailable"


def test_invalid_port_is_blocked_before_provider(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-invalid-port",
    )
    claim = _claim(port=70000)

    result = spine.verify_reality(
        claims=(claim,),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "local_tcp_claim_invalid_port" in result.receipt.limitations


def test_address_filter_is_passed_exactly(tmp_path: Path) -> None:
    provider = FakeTcpProvider(
        _observation(port=11434, address="127.0.0.1", listening=True)
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-address",
    )

    result = spine.verify_reality(
        claims=(_claim(port=11434, address="127.0.0.1"),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert provider.calls == [(11434, "127.0.0.1")]
    assert result.claim_results[0]["local_address"] == "127.0.0.1"


def test_tcp_verifier_does_not_expand_authority(tmp_path: Path) -> None:
    provider = FakeTcpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_socket.read"],
        task_id="tcp-authority",
    )
    before = spine.core.authority

    result = spine.verify_reality(
        claims=(_claim(),),
        tcp_listener_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
