"""Local federation discovery primitives with graceful optional zeroconf support."""

from __future__ import annotations

import hashlib
import socket
from datetime import datetime, timezone
from typing import TypedDict, cast

from phios import __version__
from phios.core.lt_engine import compute_lt
from phios.core.tbrc_bridge import TBRCBridge


class PhiPeerDict(TypedDict):
    node_name: str
    address: str
    port: int
    phios_version: str
    lt_score: float
    tbrc: bool
    phb: bool
    last_seen: str
    reachable: bool


class PhiNodeAnnouncer:
    SERVICE_TYPE = "_phios._tcp.local."
    DEFAULT_PORT = 36900

    def __init__(self) -> None:
        self.active = False
        self._zeroconf: object | None = None
        self._service_info: object | None = None
        self._last_reason = "not announced"
        self._properties: dict[str, str] = {}

    def _safe_node_name(self, node_name: str) -> str:
        if node_name.strip():
            return node_name.strip()
        return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]

    def _build_properties(self, node_name: str, lt_score: float | None = None) -> dict[str, str]:
        bridge = TBRCBridge()
        phb_status = bridge.get_phb_status()
        lt_value = float(compute_lt().get("lt", 0.5)) if lt_score is None else float(lt_score)
        return {
            "node_name": self._safe_node_name(node_name),
            "phios_version": str(__version__),
            "lt_score": f"{lt_value:.2f}",
            "tbrc": "yes" if bridge.is_available() else "no",
            "phb": "yes" if bool(phb_status.get("connected", False)) else "no",
        }

    def preview_payload(self, node_name: str) -> dict[str, str]:
        self._properties = self._build_properties(node_name)
        return dict(self._properties)

    def announce(self, node_name: str, operator_confirmed: bool = False) -> bool:
        if not operator_confirmed:
            self._last_reason = "operator confirmation required"
            return False
        self._properties = self._build_properties(node_name)
        try:
            from zeroconf import ServiceInfo, Zeroconf  # type: ignore[import-not-found]
        except Exception:
            self._last_reason = "zeroconf unavailable"
            self.active = False
            return False

        try:
            self._zeroconf = Zeroconf()
            info = ServiceInfo(
                self.SERVICE_TYPE,
                f"{self._properties['node_name']}.{self.SERVICE_TYPE}",
                addresses=[socket.inet_aton("127.0.0.1")],
                port=self.DEFAULT_PORT,
                properties={k: v.encode("utf-8") for k, v in self._properties.items()},
            )
            cast(object, self._zeroconf).register_service(info)  # type: ignore[attr-defined]
            self._service_info = info
            self.active = True
            self._last_reason = "ok"
            return True
        except Exception:
            self.active = False
            self._last_reason = "announce failed"
            return False

    def stop(self) -> None:
        try:
            if self._zeroconf is not None and self._service_info is not None:
                cast(object, self._zeroconf).unregister_service(self._service_info)  # type: ignore[attr-defined]
                cast(object, self._zeroconf).close()  # type: ignore[attr-defined]
        except Exception:
            pass
        self._zeroconf = None
        self._service_info = None
        self.active = False

    def update_lt(self, lt_score: float) -> None:
        self._properties["lt_score"] = f"{float(lt_score):.2f}"
        if not self.active:
            return
        try:
            if self._service_info is not None and hasattr(self._service_info, "properties"):
                props = dict(getattr(self._service_info, "properties", {}))
                props[b"lt_score"] = self._properties["lt_score"].encode("utf-8")
                setattr(self._service_info, "properties", props)
        except Exception:
            return

    def status(self) -> dict[str, object]:
        return {
            "active": self.active,
            "last_reason": self._last_reason,
            "announced": dict(self._properties),
        }


class PhiNodeDiscovery:
    DEFAULT_PORT = 36900

    def __init__(self) -> None:
        self.active = False
        self._last_reason = "offline"
        self._peers: dict[str, PhiPeerDict] = {}

    def start_listening(self) -> None:
        try:
            from zeroconf import Zeroconf  # type: ignore[import-not-found,unused-ignore]

            _ = Zeroconf
            self.active = True
            self._last_reason = "listening"
        except Exception:
            self.active = False
            self._last_reason = "zeroconf unavailable"

    def stop_listening(self) -> None:
        self.active = False
        self._last_reason = "stopped"
        self._peers = {}

    def _sanitize(self, peer: PhiPeerDict) -> PhiPeerDict:
        return {
            "node_name": peer["node_name"],
            "address": peer["address"],
            "port": int(peer["port"]),
            "phios_version": peer["phios_version"],
            "lt_score": float(peer["lt_score"]),
            "tbrc": bool(peer["tbrc"]),
            "phb": bool(peer["phb"]),
            "last_seen": peer["last_seen"],
            "reachable": bool(peer["reachable"]),
        }

    def get_peers(self) -> list[PhiPeerDict]:
        if not self.active:
            return []
        return [self._sanitize(p) for p in self._peers.values()]

    def ping_peer(self, address: str) -> bool:
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection((address, self.DEFAULT_PORT), timeout=0.5)
            return True
        except Exception:
            return False
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def inject_peer_for_tests(self, peer: PhiPeerDict) -> None:
        self._peers[peer["address"]] = self._sanitize(peer)
        self._peers[peer["address"]]["last_seen"] = datetime.now(timezone.utc).isoformat()

    def status(self) -> dict[str, object]:
        return {"active": self.active, "last_reason": self._last_reason, "peer_count": len(self.get_peers())}
