from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phios.phivessel_handshake import (
    PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION,
    PhiVesselHandshakeError,
    PhiVesselHostHandshakeService,
    PhiVesselSessionOperation,
)

BRIDGE_VERSION = "PV-PHIOS-BRIDGE-0.1"
TOKEN = "a" * 64
NOW = datetime(2026, 9, 27, 23, 30, 0, tzinfo=UTC)


def _service(
    *,
    now: list[datetime] | None = None,
    available: tuple[PhiVesselSessionOperation, ...] = (
        PhiVesselSessionOperation.OBSERVE,
        PhiVesselSessionOperation.PROPOSE,
        PhiVesselSessionOperation.EXECUTE,
    ),
) -> PhiVesselHostHandshakeService:
    clock = now if now is not None else [NOW]
    return PhiVesselHostHandshakeService(
        bridge_version=BRIDGE_VERSION,
        available_operations=available,
        session_ttl_seconds=60,
        clock=lambda: clock[0],
        token_factory=lambda: TOKEN,
    )


def test_handshake_creates_zero_authority_transport_session() -> None:
    service = _service()

    result = service.handshake(
        client_instance_id="super-phivessel:desktop:local",
        client_nonce="nonce_0123456789abcdef",
        supported_bridge_versions=(
            "PV-PHIOS-BRIDGE-0.0",
            BRIDGE_VERSION,
        ),
        requested_operations=(
            PhiVesselSessionOperation.OBSERVE,
            PhiVesselSessionOperation.EXECUTE,
        ),
    )

    assert result.handshake_protocol_version == (
        PHIVESSEL_HANDSHAKE_PROTOCOL_VERSION
    )
    assert result.selected_bridge_version == BRIDGE_VERSION
    assert result.granted_operations == (
        PhiVesselSessionOperation.OBSERVE,
        PhiVesselSessionOperation.EXECUTE,
    )
    assert result.session_token == TOKEN
    assert result.client_identity_authenticated is False
    assert result.transport_session_only is True
    assert result.action_lease_still_required_for_execution is True
    assert result.policy_authority is False
    assert result.action_authority is False
    assert result.execution_authority is False
    assert result.effect_performed is False

    session = service.validate(
        session_id=result.session_id,
        session_token=TOKEN,
        operation=PhiVesselSessionOperation.OBSERVE,
    )
    assert session.client_instance_id == "super-phivessel:desktop:local"
    assert session.client_identity_authenticated is False
    assert session.action_authority is False
    assert session.execution_authority is False


def test_handshake_grants_only_currently_available_operations() -> None:
    service = _service(
        available=(
            PhiVesselSessionOperation.OBSERVE,
            PhiVesselSessionOperation.PROPOSE,
        )
    )

    result = service.handshake(
        client_instance_id="super-phivessel:desktop:local",
        client_nonce="nonce_0123456789abcdef",
        supported_bridge_versions=(BRIDGE_VERSION,),
        requested_operations=(
            PhiVesselSessionOperation.OBSERVE,
            PhiVesselSessionOperation.EXECUTE,
        ),
    )

    assert result.granted_operations == (
        PhiVesselSessionOperation.OBSERVE,
    )
    with pytest.raises(
        PhiVesselHandshakeError,
        match="was not negotiated",
    ):
        service.validate(
            session_id=result.session_id,
            session_token=TOKEN,
            operation=PhiVesselSessionOperation.EXECUTE,
        )


def test_handshake_rejects_unsupported_bridge_version() -> None:
    service = _service()

    with pytest.raises(
        PhiVesselHandshakeError,
        match="no mutually supported",
    ):
        service.handshake(
            client_instance_id="super-phivessel:desktop:local",
            client_nonce="nonce_0123456789abcdef",
            supported_bridge_versions=("PV-PHIOS-BRIDGE-9.9",),
            requested_operations=(
                PhiVesselSessionOperation.OBSERVE,
            ),
        )


def test_session_rejects_wrong_bearer_token() -> None:
    service = _service()
    result = service.handshake(
        client_instance_id="super-phivessel:desktop:local",
        client_nonce="nonce_0123456789abcdef",
        supported_bridge_versions=(BRIDGE_VERSION,),
        requested_operations=(PhiVesselSessionOperation.OBSERVE,),
    )

    with pytest.raises(
        PhiVesselHandshakeError,
        match="token does not match",
    ):
        service.validate(
            session_id=result.session_id,
            session_token="b" * 64,
            operation=PhiVesselSessionOperation.OBSERVE,
        )


def test_session_expires_and_is_removed() -> None:
    now = [NOW]
    service = _service(now=now)
    result = service.handshake(
        client_instance_id="super-phivessel:desktop:local",
        client_nonce="nonce_0123456789abcdef",
        supported_bridge_versions=(BRIDGE_VERSION,),
        requested_operations=(PhiVesselSessionOperation.OBSERVE,),
    )

    now[0] = NOW + timedelta(seconds=61)

    with pytest.raises(
        PhiVesselHandshakeError,
        match="absent or expired",
    ):
        service.validate(
            session_id=result.session_id,
            session_token=TOKEN,
            operation=PhiVesselSessionOperation.OBSERVE,
        )


def test_new_host_instance_invalidates_old_session_by_construction() -> None:
    first = _service()
    second = _service()
    result = first.handshake(
        client_instance_id="super-phivessel:desktop:local",
        client_nonce="nonce_0123456789abcdef",
        supported_bridge_versions=(BRIDGE_VERSION,),
        requested_operations=(PhiVesselSessionOperation.OBSERVE,),
    )

    assert first.server_instance_id != second.server_instance_id
    with pytest.raises(
        PhiVesselHandshakeError,
        match="absent or expired",
    ):
        second.validate(
            session_id=result.session_id,
            session_token=TOKEN,
            operation=PhiVesselSessionOperation.OBSERVE,
        )
