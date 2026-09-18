from __future__ import annotations

from .models import Capability


class CapabilityRegistry:
    """Small, explicit registry. Unknown capabilities are never executable."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.id in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.id}")
        self._capabilities[capability.id] = capability

    def get(self, capability_id: str) -> Capability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unknown capability: {capability_id}") from exc

    def list(self) -> list[Capability]:
        return sorted(self._capabilities.values(), key=lambda item: item.id)
