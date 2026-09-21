"""Strict Covenant topology for CR-01.

ROOT is represented so the contract can reject it explicitly. It is not an actor
execution destination and is not part of the actor transition graph.
"""

from __future__ import annotations

from enum import Enum


class TrustZone(str, Enum):
    EXTERNAL = "EXTERNAL"
    INTAKE = "INTAKE"
    IDENTIFIED = "IDENTIFIED"
    BOUNDED = "BOUNDED"
    GOVERNED_EXECUTION = "GOVERNED_EXECUTION"
    OBSERVED = "OBSERVED"
    VERIFIED_OUTPUT = "VERIFIED_OUTPUT"
    ROOT = "ROOT"


_ACTOR_ZONES = frozenset(
    {
        TrustZone.EXTERNAL,
        TrustZone.INTAKE,
        TrustZone.IDENTIFIED,
        TrustZone.BOUNDED,
        TrustZone.GOVERNED_EXECUTION,
        TrustZone.OBSERVED,
        TrustZone.VERIFIED_OUTPUT,
    }
)

_ALLOWED_TRANSITIONS = frozenset(
    {
        (TrustZone.EXTERNAL, TrustZone.INTAKE),
        (TrustZone.INTAKE, TrustZone.IDENTIFIED),
        (TrustZone.IDENTIFIED, TrustZone.BOUNDED),
        (TrustZone.BOUNDED, TrustZone.GOVERNED_EXECUTION),
        (TrustZone.GOVERNED_EXECUTION, TrustZone.OBSERVED),
        (TrustZone.OBSERVED, TrustZone.VERIFIED_OUTPUT),
    }
)


def actor_zones() -> tuple[TrustZone, ...]:
    """Return actor zones in deterministic topology order."""

    return (
        TrustZone.EXTERNAL,
        TrustZone.INTAKE,
        TrustZone.IDENTIFIED,
        TrustZone.BOUNDED,
        TrustZone.GOVERNED_EXECUTION,
        TrustZone.OBSERVED,
        TrustZone.VERIFIED_OUTPUT,
    )


def allowed_transitions() -> tuple[tuple[TrustZone, TrustZone], ...]:
    """Return legal actor transitions in deterministic topology order."""

    zones = actor_zones()
    return tuple(zip(zones, zones[1:]))


def require_actor_zone(zone: TrustZone) -> TrustZone:
    """Reject ROOT or any non-actor zone from actor runtime context."""

    if zone not in _ACTOR_ZONES:
        raise ValueError("ROOT authority plane cannot be used as an actor zone")
    return zone


def require_transition(source: TrustZone, target: TrustZone) -> None:
    """Reject any crossing outside the strict CR-01 actor topology."""

    require_actor_zone(source)
    require_actor_zone(target)
    if (source, target) not in _ALLOWED_TRANSITIONS:
        raise ValueError(
            f"illegal Covenant boundary transition: {source.value} -> {target.value}"
        )
