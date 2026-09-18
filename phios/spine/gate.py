from __future__ import annotations

from collections.abc import Iterable

from .models import Capability, PermissionDecision


class PermissionGate:
    """Fail-closed permission gate for the v0.1 spine."""

    def __init__(self, allowed_permissions: Iterable[str] = ()) -> None:
        self._allowed = frozenset(allowed_permissions)

    def evaluate(self, capability: Capability) -> PermissionDecision:
        requested = tuple(capability.permissions)
        granted = tuple(p for p in requested if p in self._allowed)
        denied = tuple(p for p in requested if p not in self._allowed)
        allowed = not denied
        if allowed:
            reason = "All requested permissions are explicitly granted."
        else:
            reason = "Denied by fail-closed policy: " + ", ".join(denied)
        return PermissionDecision(
            allowed=allowed,
            requested=requested,
            granted=granted,
            denied=denied,
            reason=reason,
        )
