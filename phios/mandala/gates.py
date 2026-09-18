from __future__ import annotations

from typing import Protocol

from .contracts import Gate, MandalaPacket, PhiCoreState
from .receipts import GateReceipt


class GateContract(Protocol):
    """Semantic boundary contract implemented by a Mandala gate."""

    gate: Gate

    def cross(self, packet: MandalaPacket, core: PhiCoreState) -> GateReceipt:
        """Evaluate one typed boundary crossing and return a GateReceipt."""
        ...
