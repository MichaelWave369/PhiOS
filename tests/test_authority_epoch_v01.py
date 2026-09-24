from __future__ import annotations

import copy

import pytest

from phios.authority_epoch import (
    AUTHORITY_EPOCH_SCHEMA_VERSION,
    AuthorityEpoch,
    AuthorityEpochContractError,
)
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind


POLICY = "a" * 64


def _event(
    event_id: str,
    sequence: int,
    kind: AuthorityEventKind,
    permission: str,
    effective_at: str,
    *,
    expires_at: str | None = None,
    authority_source: str = "operator-ledger",
) -> AuthoritativeAuthorityEvent:
    return AuthoritativeAuthorityEvent(
        event_id=event_id,
        sequence=sequence,
        kind=kind,
        permission=permission,
        authority_source=authority_source,
        effective_at=effective_at,
        expires_at=expires_at,
    )


def _events() -> tuple[AuthoritativeAuthorityEvent, ...]:
    return (
        _event(
            "grant-memory",
            1,
            AuthorityEventKind.GRANT,
            "memory.read",
            "2026-09-24T01:00:00+00:00",
        ),
        _event(
            "grant-shell",
            2,
            AuthorityEventKind.GRANT,
            "shell.exec",
            "2026-09-24T01:01:00+00:00",
            expires_at="2026-09-24T01:10:00+00:00",
        ),
        _event(
            "revoke-memory",
            3,
            AuthorityEventKind.REVOKE,
            "memory.read",
            "2026-09-24T01:02:00+00:00",
        ),
        _event(
            "future-grant",
            4,
            AuthorityEventKind.GRANT,
            "memory.read",
            "2026-09-24T01:08:00+00:00",
            authority_source="scheduled-policy",
        ),
    )


def _epoch() -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("shell.exec", "memory.read"),
        events=_events(),
        observed_at="2026-09-24T01:03:00+00:00",
    )


def test_authority_epoch_is_deterministic_and_zero_authority() -> None:
    epoch = _epoch()
    payload = epoch.to_dict()

    assert epoch.schema_version == AUTHORITY_EPOCH_SCHEMA_VERSION
    assert epoch.ceiling == ("memory.read", "shell.exec")
    assert epoch.grants == ("shell.exec",)
    assert epoch.authority_sources == (
        "operator-ledger",
        "scheduled-policy",
    )
    assert epoch.applied_event_ids == (
        "grant-memory",
        "grant-shell",
        "revoke-memory",
    )
    assert epoch.active_grant_event_ids == ("grant-shell",)
    assert epoch.next_known_transition_at == (
        "2026-09-24T01:08:00+00:00"
    )
    assert payload["effect_performed"] is False
    assert payload["operational_authority"] is False
    assert payload["action_authority"] is False
    assert payload["execution_authority"] is False
    assert len(payload["authority_epoch_sha256"]) == 64

    replay = AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("memory.read", "shell.exec"),
        events=tuple(reversed(_events())),
        observed_at="2026-09-24T01:03:00+00:00",
    )
    assert replay == epoch
    assert replay.authority_epoch_sha256 == epoch.authority_epoch_sha256


def test_authority_epoch_round_trips_exactly() -> None:
    epoch = _epoch()

    parsed = AuthorityEpoch.from_dict(epoch.to_dict())

    assert parsed == epoch
    assert parsed.authority_epoch_sha256 == epoch.authority_epoch_sha256


def test_future_known_event_changes_epoch_without_becoming_current_grant() -> None:
    baseline_events = _events()[:-1]
    baseline = AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("memory.read", "shell.exec"),
        events=baseline_events,
        observed_at="2026-09-24T01:03:00+00:00",
    )
    scheduled = _epoch()

    assert baseline.grants == scheduled.grants
    assert baseline.authority_epoch_sha256 != scheduled.authority_epoch_sha256
    assert baseline.next_known_transition_at == (
        "2026-09-24T01:10:00+00:00"
    )
    assert scheduled.next_known_transition_at == (
        "2026-09-24T01:08:00+00:00"
    )


def test_active_grant_expiry_is_the_next_known_transition() -> None:
    epoch = AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("shell.exec",),
        events=(
            _event(
                "grant-shell",
                1,
                AuthorityEventKind.GRANT,
                "shell.exec",
                "2026-09-24T01:00:00+00:00",
                expires_at="2026-09-24T01:05:00+00:00",
            ),
        ),
        observed_at="2026-09-24T01:03:00+00:00",
    )

    assert epoch.grants == ("shell.exec",)
    assert epoch.next_known_transition_at == (
        "2026-09-24T01:05:00+00:00"
    )


def test_revocation_changes_authority_state_and_revocation_digest() -> None:
    grants_only = _events()[:2]
    with_revocation = _events()[:3]

    before = AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("memory.read", "shell.exec"),
        events=grants_only,
        observed_at="2026-09-24T01:03:00+00:00",
    )
    after = AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("memory.read", "shell.exec"),
        events=with_revocation,
        observed_at="2026-09-24T01:03:00+00:00",
    )

    assert before.grants == ("memory.read", "shell.exec")
    assert after.grants == ("shell.exec",)
    assert before.revocation_set_sha256 != after.revocation_set_sha256
    assert before.authority_context_sha256 != after.authority_context_sha256
    assert before.authority_epoch_sha256 != after.authority_epoch_sha256


def test_policy_change_changes_epoch_identity_without_minting_authority() -> None:
    first = _epoch()
    second = AuthorityEpoch.build(
        principal_id=first.principal_id,
        policy_sha256="b" * 64,
        ceiling=("memory.read", "shell.exec"),
        events=_events(),
        observed_at=first.observed_at,
    )

    assert first.grants == second.grants
    assert first.authority_epoch_sha256 != second.authority_epoch_sha256
    assert second.action_authority is False
    assert second.execution_authority is False


def test_principal_change_changes_epoch_identity() -> None:
    first = _epoch()
    second = AuthorityEpoch.build(
        principal_id="service:builder",
        policy_sha256=POLICY,
        ceiling=("memory.read", "shell.exec"),
        events=_events(),
        observed_at=first.observed_at,
    )

    assert first.authority_epoch_sha256 != second.authority_epoch_sha256


def test_epoch_rejects_duplicate_authority_event_ids() -> None:
    events = (
        _event(
            "duplicate",
            1,
            AuthorityEventKind.GRANT,
            "memory.read",
            "2026-09-24T01:00:00+00:00",
        ),
        _event(
            "duplicate",
            2,
            AuthorityEventKind.REVOKE,
            "memory.read",
            "2026-09-24T01:01:00+00:00",
        ),
    )

    with pytest.raises(
        AuthorityEpochContractError,
        match="event IDs must be unique",
    ):
        AuthorityEpoch.build(
            principal_id="operator:michael",
            policy_sha256=POLICY,
            ceiling=("memory.read",),
            events=events,
            observed_at="2026-09-24T01:03:00+00:00",
        )


def test_epoch_cannot_widen_authority_projection_ceiling() -> None:
    with pytest.raises(
        AuthorityEpochContractError,
        match="exceeds the frozen ceiling",
    ):
        AuthorityEpoch.build(
            principal_id="operator:michael",
            policy_sha256=POLICY,
            ceiling=("memory.read",),
            events=(
                _event(
                    "bad-grant",
                    1,
                    AuthorityEventKind.GRANT,
                    "shell.exec",
                    "2026-09-24T01:00:00+00:00",
                ),
            ),
            observed_at="2026-09-24T01:03:00+00:00",
        )


def test_serialized_epoch_rejects_authority_smuggling() -> None:
    payload = _epoch().to_dict()
    payload["execution_authority"] = True

    with pytest.raises(
        AuthorityEpochContractError,
        match="cannot itself carry",
    ):
        AuthorityEpoch.from_dict(payload)


def test_serialized_epoch_rejects_claimed_execution() -> None:
    payload = _epoch().to_dict()
    payload["effect_performed"] = True

    with pytest.raises(
        AuthorityEpochContractError,
        match="cannot claim an effect",
    ):
        AuthorityEpoch.from_dict(payload)


def test_serialized_epoch_rejects_tampered_authority_context() -> None:
    payload = _epoch().to_dict()
    payload["grants"] = ["memory.read", "shell.exec"]

    with pytest.raises(
        AuthorityEpochContractError,
        match="authority_context_sha256 does not match",
    ):
        AuthorityEpoch.from_dict(payload)


def test_serialized_epoch_rejects_tampered_epoch_digest() -> None:
    payload = copy.deepcopy(_epoch().to_dict())
    payload["authority_epoch_sha256"] = "f" * 64

    with pytest.raises(
        AuthorityEpochContractError,
        match="does not match canonical",
    ):
        AuthorityEpoch.from_dict(payload)


def test_empty_authority_state_is_valid_and_has_no_known_transition() -> None:
    epoch = AuthorityEpoch.build(
        principal_id="service:observer",
        policy_sha256=POLICY,
        ceiling=("memory.read",),
        events=(),
        observed_at="2026-09-24T01:03:00+00:00",
    )

    assert epoch.grants == ()
    assert epoch.authority_sources == ()
    assert epoch.known_event_ids == ()
    assert epoch.applied_event_ids == ()
    assert epoch.next_known_transition_at is None
    assert epoch.action_authority is False
    assert epoch.execution_authority is False
