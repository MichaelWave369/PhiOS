from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Risk = Literal["read", "low", "medium", "high"]


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    description: str
    permissions: tuple[str, ...] = field(default_factory=tuple)
    risk: Risk = "low"
    version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["permissions"] = list(self.permissions)
        return data


@dataclass(frozen=True)
class PhiPlan:
    capability_id: str
    payload: dict[str, Any]
    planner: str = "phivessel.spine.deterministic"
    planner_version: str = "0.1.0"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requested: tuple[str, ...]
    granted: tuple[str, ...]
    denied: tuple[str, ...]
    reason: str


@dataclass
class ExecutionReceipt:
    schema_version: str
    receipt_id: str
    timestamp_utc: str
    capability_id: str
    planner: str
    input_sha256: str
    permissions_requested: list[str]
    permission_status: str
    execution_status: str
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    error: str | None = None
    packet_id: str | None = None
    gate_receipt_id: str | None = None
    action_receipt_id: str | None = None
    mandala_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
