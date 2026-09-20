"""Provider-neutral PhiReflex contracts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping


ROLE_LABELS = ("utility", "builder", "synthesis", "translator", "ledger")
RISK_LABELS = ("low", "elevated", "high")


class ReflexContractError(ValueError):
    """Raised when a PhiReflex contract is malformed."""


@dataclass(frozen=True, slots=True)
class ReflexInput:
    task_text: str
    tool_intent: bool = False
    external_side_effect: bool = False

    def to_dict(self) -> dict[str, object]:
        text = self.task_text.strip()
        if not text:
            raise ReflexContractError("task_text must be non-empty")
        return {
            "task_text": text,
            "tool_intent": self.tool_intent,
            "external_side_effect": self.external_side_effect,
        }


@dataclass(frozen=True, slots=True)
class ReflexDecision:
    provider: str
    provider_version: str
    model: str
    role: str
    role_probabilities: tuple[tuple[str, float], ...]
    risk: str
    risk_probabilities: tuple[tuple[str, float], ...]
    needs_system2_probability: float
    needs_verification_probability: float
    confidence: float
    latency_ms: float
    action_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ReflexContractError("provider must be non-empty")
        if not self.provider_version.strip():
            raise ReflexContractError("provider_version must be non-empty")
        if not self.model.strip():
            raise ReflexContractError("model must be non-empty")
        if self.role not in ROLE_LABELS:
            raise ReflexContractError("role is outside the PhiReflex v0.1 role set")
        if self.risk not in RISK_LABELS:
            raise ReflexContractError("risk is outside the PhiReflex v0.1 risk set")
        _validate_distribution(self.role_probabilities, ROLE_LABELS, "role")
        _validate_distribution(self.risk_probabilities, RISK_LABELS, "risk")
        for label, value in (
            ("needs_system2_probability", self.needs_system2_probability),
            ("needs_verification_probability", self.needs_verification_probability),
            ("confidence", self.confidence),
        ):
            _require_probability(value, label)
        if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
            raise ReflexContractError("latency_ms must be finite and non-negative")
        if self.action_authority is not False:
            raise ReflexContractError("PhiReflex decisions cannot carry action authority")
        if self.execution_authority is not False:
            raise ReflexContractError("PhiReflex decisions cannot carry execution authority")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "provider_version": self.provider_version,
            "model": self.model,
            "role": self.role,
            "role_probabilities": dict(self.role_probabilities),
            "risk": self.risk,
            "risk_probabilities": dict(self.risk_probabilities),
            "needs_system2_probability": self.needs_system2_probability,
            "needs_verification_probability": self.needs_verification_probability,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, slots=True)
class ReflexShadowReceipt:
    schema: str
    input_sha256: str
    baseline: ReflexDecision
    shadow_status: str
    shadow: ReflexDecision | None
    shadow_provider: str
    shadow_reason: str | None
    role_agreement: bool | None
    risk_agreement: bool | None
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "input_sha256": self.input_sha256,
            "baseline": self.baseline.to_dict(),
            "shadow_status": self.shadow_status,
            "shadow": self.shadow.to_dict() if self.shadow else None,
            "shadow_provider": self.shadow_provider,
            "shadow_reason": self.shadow_reason,
            "role_agreement": self.role_agreement,
            "risk_agreement": self.risk_agreement,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


def build_shadow_receipt(
    *,
    reflex_input: ReflexInput,
    baseline: ReflexDecision,
    shadow_status: str,
    shadow: ReflexDecision | None,
    shadow_provider: str,
    shadow_reason: str | None,
) -> ReflexShadowReceipt:
    if shadow_status not in {"ok", "unavailable", "error"}:
        raise ReflexContractError("unsupported shadow_status")
    if shadow_status == "ok" and shadow is None:
        raise ReflexContractError("ok shadow status requires a shadow decision")
    if shadow_status != "ok" and shadow is not None:
        raise ReflexContractError("non-ok shadow status cannot carry a decision")
    input_payload = reflex_input.to_dict()
    input_sha256 = _digest(input_payload)
    role_agreement = None if shadow is None else baseline.role == shadow.role
    risk_agreement = None if shadow is None else baseline.risk == shadow.risk
    payload: dict[str, object] = {
        "schema": "phios.reflex_shadow_receipt.v0.1",
        "input_sha256": input_sha256,
        "baseline": baseline.to_dict(),
        "shadow_status": shadow_status,
        "shadow": shadow.to_dict() if shadow else None,
        "shadow_provider": shadow_provider,
        "shadow_reason": shadow_reason,
        "role_agreement": role_agreement,
        "risk_agreement": risk_agreement,
        "action_authority": False,
        "execution_authority": False,
    }
    return ReflexShadowReceipt(
        schema="phios.reflex_shadow_receipt.v0.1",
        input_sha256=input_sha256,
        baseline=baseline,
        shadow_status=shadow_status,
        shadow=shadow,
        shadow_provider=shadow_provider,
        shadow_reason=shadow_reason,
        role_agreement=role_agreement,
        risk_agreement=risk_agreement,
        action_authority=False,
        execution_authority=False,
        receipt_sha256=_digest(payload),
    )


def normalized_distribution(
    values: Mapping[str, float],
    labels: tuple[str, ...],
) -> tuple[tuple[str, float], ...]:
    if set(values) != set(labels):
        raise ReflexContractError("probability labels do not match declared labels")
    cleaned = {label: _require_probability(values[label], label) for label in labels}
    total = sum(cleaned.values())
    if total <= 0:
        raise ReflexContractError("probability distribution must have positive mass")
    return tuple((label, cleaned[label] / total) for label in labels)


def confidence_for(
    distribution: tuple[tuple[str, float], ...],
) -> float:
    return max(value for _, value in distribution)


def _validate_distribution(
    distribution: tuple[tuple[str, float], ...],
    labels: tuple[str, ...],
    name: str,
) -> None:
    if tuple(label for label, _ in distribution) != labels:
        raise ReflexContractError(f"{name} probability labels/order are invalid")
    total = 0.0
    for label, value in distribution:
        total += _require_probability(value, label)
    if abs(total - 1.0) > 1e-6:
        raise ReflexContractError(f"{name} probabilities must sum to 1")


def _require_probability(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ReflexContractError(f"{label} must be a probability in [0, 1]")
    return number


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReflexContractError("PhiReflex payload must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
