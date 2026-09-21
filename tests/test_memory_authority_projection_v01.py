import pytest

from phios.mandala import (
    AuthoritativeAuthorityEvent,
    AuthorityEventKind,
    AuthorityProjection,
    AuthorityProjectionError,
)


def _event(
    event_id: str,
    sequence: int,
    kind: AuthorityEventKind,
    permission: str,
    effective_at: str,
    *,
    expires_at: str | None = None,
) -> AuthoritativeAuthorityEvent:
    return AuthoritativeAuthorityEvent(
        event_id=event_id,
        sequence=sequence,
        kind=kind,
        permission=permission,
        authority_source="operator-ledger",
        effective_at=effective_at,
        expires_at=expires_at,
    )


def test_projection_replays_grant_revoke_and_expiry_deterministically() -> None:
    events = (
        _event(
            "grant-read",
            1,
            AuthorityEventKind.GRANT,
            "memory.read",
            "2026-09-21T06:00:00+00:00",
        ),
        _event(
            "grant-shell",
            2,
            AuthorityEventKind.GRANT,
            "shell.exec",
            "2026-09-21T06:01:00+00:00",
            expires_at="2026-09-21T06:05:00+00:00",
        ),
        _event(
            "revoke-read",
            3,
            AuthorityEventKind.REVOKE,
            "memory.read",
            "2026-09-21T06:02:00+00:00",
        ),
    )
    first = AuthorityProjection.project(
        ceiling=("shell.exec", "memory.read"),
        events=events,
        observed_at="2026-09-21T06:03:00+00:00",
    )
    replay = AuthorityProjection.project(
        ceiling=("memory.read", "shell.exec"),
        events=tuple(reversed(events)),
        observed_at="2026-09-21T06:03:00+00:00",
    )

    assert first == replay
    assert first.grants == ("shell.exec",)
    assert first.active_grant_event_ids == ("grant-shell",)
    assert first.to_authority_context().allows("shell.exec") is True
    assert first.to_authority_context().allows("memory.read") is False

    expired = AuthorityProjection.project(
        ceiling=("memory.read", "shell.exec"),
        events=events,
        observed_at="2026-09-21T06:06:00+00:00",
    )
    assert expired.grants == ()


def test_projection_cannot_widen_the_frozen_ceiling() -> None:
    with pytest.raises(AuthorityProjectionError, match="exceeds the frozen ceiling"):
        AuthorityProjection.project(
            ceiling=("memory.read",),
            events=(
                _event(
                    "bad-grant",
                    1,
                    AuthorityEventKind.GRANT,
                    "shell.exec",
                    "2026-09-21T06:00:00+00:00",
                ),
            ),
            observed_at="2026-09-21T06:01:00+00:00",
        )


def test_future_events_do_not_become_present_authority() -> None:
    result = AuthorityProjection.project(
        ceiling=("memory.read",),
        events=(
            _event(
                "future",
                1,
                AuthorityEventKind.GRANT,
                "memory.read",
                "2026-09-21T07:00:00+00:00",
            ),
        ),
        observed_at="2026-09-21T06:00:00+00:00",
    )

    assert result.grants == ()
    assert result.source_event_ids == ()
