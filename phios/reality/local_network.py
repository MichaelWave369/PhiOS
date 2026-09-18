from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class InterfaceObservationError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class InterfaceObservation:
    interface_name: str
    is_up: bool
    duplex: int
    speed_mbps: int
    mtu: int
    provider: str
    provider_version: str | None
    captured_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InterfaceStateProvider(Protocol):
    name: str

    def observe(self, interface_name: str) -> InterfaceObservation | None:
        ...


class PsutilInterfaceStateProvider:
    """Observe one exact local interface using psutil.net_if_stats()."""

    name = "psutil.net_if_stats"

    def observe(self, interface_name: str) -> InterfaceObservation | None:
        try:
            import psutil
        except ImportError as exc:
            raise InterfaceObservationError("psutil is unavailable") from exc

        try:
            stats = psutil.net_if_stats()
        except Exception as exc:  # noqa: BLE001 - platform/provider boundary
            raise InterfaceObservationError("local interface state is unavailable") from exc

        item = stats.get(interface_name)
        if item is None:
            return None

        return InterfaceObservation(
            interface_name=interface_name,
            is_up=bool(item.isup),
            duplex=int(item.duplex),
            speed_mbps=int(item.speed),
            mtu=int(item.mtu),
            provider=self.name,
            provider_version=str(getattr(psutil, "__version__", "")) or None,
            captured_at_utc=datetime.now(UTC).isoformat(),
        )
