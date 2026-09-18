import json
from pathlib import Path

from phios.mandala import MandalaStatus
from phios.reality import (
    InterfaceObservation,
    InterfaceObservationError,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
)
from phios.spine.runtime import PhiOSSpine


class FakeInterfaceProvider:
    name = "fake-interface"

    def __init__(
        self,
        observations: dict[str, InterfaceObservation | None] | None = None,
        *,
        error: InterfaceObservationError | None = None,
    ) -> None:
        self.observations = observations or {}
        self.error = error
        self.calls: list[str] = []

    def observe(self, interface_name: str) -> InterfaceObservation | None:
        self.calls.append(interface_name)
        if self.error is not None:
            raise self.error
        return self.observations.get(interface_name)


def _observation(name: str, *, is_up: bool) -> InterfaceObservation:
    return InterfaceObservation(
        interface_name=name,
        is_up=is_up,
        duplex=2,
        speed_mbps=1000,
        mtu=1500,
        provider="fake-interface",
        provider_version="1.0",
        captured_at_utc="2026-09-18T16:30:00+00:00",
    )


def _claim(name: str = "Ethernet", *, expected_is_up: bool = True) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_INTERFACE_STATE,
        statement=f"Local interface {name} is {'up' if expected_is_up else 'down'}.",
        interface_name=name,
        expected_is_up=expected_is_up,
    )


def test_local_interface_still_requires_reality_verify(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.local_interface.read"],
        task_id="iface-base-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "missing_grant:reality.verify" in result.receipt.limitations


def test_local_interface_requires_specific_read_grant(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="iface-read-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["verdict"] == RealityVerdict.BLOCKED.value
    assert provider.calls == []
    assert (
        result.claim_results[0]["reason"]
        == "missing_grant:reality.local_interface.read"
    )


def test_direct_interface_observation_can_support_world_claim(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-supported",
    )

    result = spine.verify_reality(
        claims=(_claim(expected_is_up=True),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["observed_is_up"] is True
    assert claim_result["expected_is_up"] is True
    assert provider.calls == ["Ethernet"]

    evidence_ref = claim_result["observation_evidence_ref"]
    assert evidence_ref in result.receipt.evidence_used
    observation = json.loads(spine.soma.evidence.read_bytes(evidence_ref))
    assert observation["interface_name"] == "Ethernet"
    assert observation["is_up"] is True
    assert observation["captured_at_utc"] == "2026-09-18T16:30:00+00:00"


def test_conflicting_interface_state_is_disputed(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-conflict",
    )
    claim = _claim(expected_is_up=False)

    result = spine.verify_reality(
        claims=(claim,),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.CONTRADICTED.value
    assert result.receipt.unresolved_contradictions == (claim.claim_id,)


def test_missing_interface_is_unresolved_not_fabricated(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-missing",
    )

    result = spine.verify_reality(
        claims=(_claim("NoSuchInterface"),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.claim_results[0]["reason"] == "local_interface_not_found"
    assert result.receipt.evidence_used == ()


def test_provider_failure_is_unresolved(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider(
        error=InterfaceObservationError("provider unavailable")
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-provider-failure",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.claim_results[0]["reason"] == "local_interface_observation_unavailable"


def test_generic_world_state_stays_unresolved(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="generic-world",
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.WORLD_STATE,
        statement="The office uplink is healthy.",
    )

    result = spine.verify_reality(
        claims=(claim,),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == "world_state_requires_independent_world_verifier"
    assert provider.calls == []


def test_invalid_interface_claim_is_blocked_before_provider(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider()
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-invalid",
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_INTERFACE_STATE,
        statement="Incomplete interface claim.",
    )

    result = spine.verify_reality(
        claims=(claim,),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "local_interface_claim_requires_interface_name" in result.receipt.limitations
    assert "local_interface_claim_requires_expected_state" in result.receipt.limitations


def test_source_text_and_direct_interface_observation_can_both_be_supported(
    tmp_path: Path,
) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=False)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-mixed",
    )
    text_ref = spine.soma.evidence.put_text("Ethernet is DOWN").evidence_ref
    source_claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text says Ethernet is DOWN.",
        evidence_refs=(text_ref,),
        expected_text="Ethernet is DOWN",
    )
    interface_claim = _claim("Ethernet", expected_is_up=False)

    result = spine.verify_reality(
        claims=(source_claim, interface_claim),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.receipt.verdict_summary == {RealityVerdict.SUPPORTED.value: 2}
    assert text_ref in result.receipt.evidence_used
    assert result.claim_results[1]["observation_evidence_ref"] in result.receipt.evidence_used


def test_local_interface_verification_does_not_expand_authority(tmp_path: Path) -> None:
    provider = FakeInterfaceProvider({"Ethernet": _observation("Ethernet", is_up=True)})
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_interface.read"],
        task_id="iface-authority",
    )
    before = spine.core.authority

    result = spine.verify_reality(
        claims=(_claim(),),
        interface_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
