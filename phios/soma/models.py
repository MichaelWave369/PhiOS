from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from phios.mandala import MandalaPacket, PerceptionReceipt


class AcuityStatus(StrEnum):
    NATIVE = "native"
    RECOVERED = "recovered"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, kw_only=True)
class NativeEvidence:
    evidence_ref: str
    sha256: str
    path: str
    media_type: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class ObservationResult:
    packet: MandalaPacket
    evidence: NativeEvidence
    receipt: PerceptionReceipt
    observation_sha256: str | None
    observation_text: str | None

    def to_dict(self, *, include_observation: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "packet": self.packet.to_dict(),
            "evidence": self.evidence.to_dict(),
            "receipt": self.receipt.to_dict(),
            "observation_sha256": self.observation_sha256,
        }
        if include_observation:
            data["observation_text"] = self.observation_text
        return data


@dataclass(frozen=True, kw_only=True)
class FileObservationResult:
    packet: MandalaPacket
    evidence: NativeEvidence | None
    receipt: PerceptionReceipt
    observation_sha256: str | None
    observation_text: str | None
    relative_path: str
    source_root_ref: str

    def to_dict(self, *, include_observation: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "packet": self.packet.to_dict(),
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "receipt": self.receipt.to_dict(),
            "observation_sha256": self.observation_sha256,
            "relative_path": self.relative_path,
            "source_root_ref": self.source_root_ref,
        }
        if include_observation:
            data["observation_text"] = self.observation_text
        return data


@dataclass(frozen=True, kw_only=True)
class ScreenObservationResult:
    packet: MandalaPacket
    evidence: NativeEvidence | None
    receipt: PerceptionReceipt
    region: dict[str, int]
    capture_backend: str
    capture_attempts: int
    observation_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet": self.packet.to_dict(),
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "receipt": self.receipt.to_dict(),
            "region": dict(self.region),
            "capture_backend": self.capture_backend,
            "capture_attempts": self.capture_attempts,
            "observation_sha256": self.observation_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class ScreenRecoveryResult:
    packet: MandalaPacket
    receipt: PerceptionReceipt
    native_evidence_ref: str
    derived_evidence: tuple[NativeEvidence, ...]
    observation_evidence_ref: str | None
    observation_sha256: str | None
    recovery_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet": self.packet.to_dict(),
            "receipt": self.receipt.to_dict(),
            "native_evidence_ref": self.native_evidence_ref,
            "derived_evidence": [item.to_dict() for item in self.derived_evidence],
            "observation_evidence_ref": self.observation_evidence_ref,
            "observation_sha256": self.observation_sha256,
            "recovery_steps": list(self.recovery_steps),
        }
