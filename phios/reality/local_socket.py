from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class TcpListenerObservationError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class TcpListenerObservation:
    local_port: int
    local_address_filter: str | None
    is_listening: bool
    matched_local_addresses: tuple[str, ...]
    provider: str
    provider_version: str | None
    captured_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TcpListenerStateProvider(Protocol):
    name: str

    def observe(
        self,
        *,
        local_port: int,
        local_address: str | None = None,
    ) -> TcpListenerObservation:
        ...


class PsutilTcpListenerStateProvider:
    """Observe one requested local TCP listener state without sending packets."""

    name = "psutil.net_connections"

    @staticmethod
    def _address_text(address: object) -> str:
        if hasattr(address, "ip"):
            return str(getattr(address, "ip"))
        if isinstance(address, tuple) and address:
            return str(address[0])
        return ""

    @staticmethod
    def _port_value(address: object) -> int | None:
        if hasattr(address, "port"):
            try:
                return int(getattr(address, "port"))
            except (TypeError, ValueError):
                return None
        if isinstance(address, tuple) and len(address) >= 2:
            try:
                return int(address[1])
            except (TypeError, ValueError):
                return None
        return None

    def observe(
        self,
        *,
        local_port: int,
        local_address: str | None = None,
    ) -> TcpListenerObservation:
        try:
            import psutil
        except ImportError as exc:
            raise TcpListenerObservationError("psutil is unavailable") from exc

        try:
            connections = psutil.net_connections(kind="tcp")
        except Exception as exc:  # noqa: BLE001 - platform/provider boundary
            raise TcpListenerObservationError("local TCP state is unavailable") from exc

        matched: list[str] = []
        listen_value = str(getattr(psutil, "CONN_LISTEN", "LISTEN"))

        for connection in connections:
            if str(connection.status) != listen_value:
                continue

            local = connection.laddr
            if self._port_value(local) != local_port:
                continue

            address_text = self._address_text(local)
            if local_address is not None and address_text != local_address:
                continue

            matched.append(address_text)

        normalized = tuple(sorted(dict.fromkeys(matched)))
        return TcpListenerObservation(
            local_port=local_port,
            local_address_filter=local_address,
            is_listening=bool(normalized),
            matched_local_addresses=normalized,
            provider=self.name,
            provider_version=str(getattr(psutil, "__version__", "")) or None,
            captured_at_utc=datetime.now(UTC).isoformat(),
        )
