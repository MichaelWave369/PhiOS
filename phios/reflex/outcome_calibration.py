"""PhiReflex v0.3 outcome calibration.

Scores shadow predictions only against explicitly observed labels. Dispatch
success/failure is provenance, not a substitute for ground truth.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from phios.reflex.models import ROLE_LABELS, RISK_LABELS


class ReflexOutcomeContractError(ValueError):
    """Raised when outcome-calibration evidence is malformed."""


@dataclass(frozen=True, slots=True)
class ReflexOutcomeObservation:
    run_id: str
    dispatch_outcome: str
    observer_label: str
    evidence_sha256: str
    actual_role: str | None = None
    actual_risk: str | None = None
    system2_needed: bool | None = None
    verification_needed: bool | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ReflexOutcomeContractError("run_id must be non-empty")
        if self.dispatch_outcome not in {
            "succeeded",
            "failed",
            "cancelled",
            "partial",
            "unknown",
        }:
            raise ReflexOutcomeContractError("unsupported dispatch_outcome")
        if not self.observer_label.strip():
            raise ReflexOutcomeContractError("observer_label must be non-empty")
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if self.actual_role is not None and self.actual_role not in ROLE_LABELS:
            raise ReflexOutcomeContractError("actual_role is outside the v0.1 role set")
        if self.actual_risk is not None and self.actual_risk not in RISK_LABELS:
            raise ReflexOutcomeContractError("actual_risk is outside the v0.1 risk set")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "dispatch_outcome": self.dispatch_outcome,
            "observer_label": self.observer_label,
            "evidence_sha256": self.evidence_sha256,
            "actual_role": self.actual_role,
            "actual_risk": self.actual_risk,
            "system2_needed": self.system2_needed,
            "verification_needed": self.verification_needed,
        }


@dataclass(frozen=True, slots=True)
class ProviderCalibration:
    provider: str
    model: str
    role_scored: bool
    role_match: bool | None
    role_brier: float | None
    risk_scored: bool
    risk_match: bool | None
    risk_brier: float | None
    system2_scored: bool
    system2_brier: float | None
    verification_scored: bool
    verification_brier: float | None
    scored_dimensions: int
    mean_brier: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "role_scored": self.role_scored,
            "role_match": self.role_match,
            "role_brier": self.role_brier,
            "risk_scored": self.risk_scored,
            "risk_match": self.risk_match,
            "risk_brier": self.risk_brier,
            "system2_scored": self.system2_scored,
            "system2_brier": self.system2_brier,
            "verification_scored": self.verification_scored,
            "verification_brier": self.verification_brier,
            "scored_dimensions": self.scored_dimensions,
            "mean_brier": self.mean_brier,
        }


@dataclass(frozen=True, slots=True)
class ReflexCalibrationReceipt:
    schema: str
    status: str
    run_id: str
    dispatch_shadow_receipt_sha256: str
    operational_context_sha256: str
    operational_plan_sha256: str
    observation: ReflexOutcomeObservation
    baseline: ProviderCalibration
    shadow_status: str
    shadow: ProviderCalibration | None
    compared_providers: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "run_id": self.run_id,
            "dispatch_shadow_receipt_sha256": self.dispatch_shadow_receipt_sha256,
            "operational_context_sha256": self.operational_context_sha256,
            "operational_plan_sha256": self.operational_plan_sha256,
            "observation": self.observation.to_dict(),
            "baseline": self.baseline.to_dict(),
            "shadow_status": self.shadow_status,
            "shadow": self.shadow.to_dict() if self.shadow else None,
            "compared_providers": self.compared_providers,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


def evaluate_dispatch_outcome(
    *,
    dispatch_shadow: Mapping[str, Any],
    observation: ReflexOutcomeObservation,
) -> ReflexCalibrationReceipt:
    """Calibrate baseline/shadow decisions against explicit observed labels."""

    shadow_obj = dict(dispatch_shadow)
    _validate_dispatch_shadow(shadow_obj)

    reflex_obj = _mapping(shadow_obj.get("reflex_receipt"), "reflex_receipt")
    baseline_decision = _mapping(reflex_obj.get("baseline"), "baseline")
    baseline = _score_provider(baseline_decision, observation)

    shadow_status = str(reflex_obj.get("shadow_status", ""))
    shadow_decision_obj = reflex_obj.get("shadow")
    shadow: ProviderCalibration | None = None
    if shadow_status == "ok":
        shadow_decision = _mapping(shadow_decision_obj, "shadow")
        shadow = _score_provider(shadow_decision, observation)
    elif shadow_decision_obj is not None:
        raise ReflexOutcomeContractError(
            "non-ok shadow status cannot carry a shadow decision"
        )

    scored = baseline.scored_dimensions
    status = "scored" if scored > 0 else "unscored_no_observed_labels"
    if shadow is not None and shadow.scored_dimensions != scored:
        raise ReflexOutcomeContractError(
            "baseline and shadow must be scored over identical observed dimensions"
        )

    payload: dict[str, object] = {
        "schema": "phios.reflex_calibration_receipt.v0.3",
        "status": status,
        "run_id": observation.run_id,
        "dispatch_shadow_receipt_sha256": str(shadow_obj["receipt_sha256"]),
        "operational_context_sha256": str(
            shadow_obj["operational_context_sha256"]
        ),
        "operational_plan_sha256": str(shadow_obj["operational_plan_sha256"]),
        "observation": observation.to_dict(),
        "baseline": baseline.to_dict(),
        "shadow_status": shadow_status,
        "shadow": shadow.to_dict() if shadow else None,
        "compared_providers": shadow is not None,
        "action_authority": False,
        "execution_authority": False,
    }
    return ReflexCalibrationReceipt(
        schema="phios.reflex_calibration_receipt.v0.3",
        status=status,
        run_id=observation.run_id,
        dispatch_shadow_receipt_sha256=str(shadow_obj["receipt_sha256"]),
        operational_context_sha256=str(
            shadow_obj["operational_context_sha256"]
        ),
        operational_plan_sha256=str(shadow_obj["operational_plan_sha256"]),
        observation=observation,
        baseline=baseline,
        shadow_status=shadow_status,
        shadow=shadow,
        compared_providers=shadow is not None,
        action_authority=False,
        execution_authority=False,
        receipt_sha256=_digest(payload),
    )


def _score_provider(
    decision: Mapping[str, Any],
    observation: ReflexOutcomeObservation,
) -> ProviderCalibration:
    provider = str(decision.get("provider", "")).strip()
    model = str(decision.get("model", "")).strip()
    if not provider or not model:
        raise ReflexOutcomeContractError(
            "provider decision requires provider and model"
        )

    role_probs = _distribution(
        decision.get("role_probabilities"),
        ROLE_LABELS,
        "role_probabilities",
    )
    risk_probs = _distribution(
        decision.get("risk_probabilities"),
        RISK_LABELS,
        "risk_probabilities",
    )
    role_choice = str(decision.get("role", ""))
    risk_choice = str(decision.get("risk", ""))
    if role_choice not in ROLE_LABELS or risk_choice not in RISK_LABELS:
        raise ReflexOutcomeContractError("provider decision has invalid labels")

    system2_p = _probability(
        decision.get("needs_system2_probability"),
        "needs_system2_probability",
    )
    verification_p = _probability(
        decision.get("needs_verification_probability"),
        "needs_verification_probability",
    )

    scores: list[float] = []
    role_brier: float | None = None
    role_match: bool | None = None
    if observation.actual_role is not None:
        role_brier = _categorical_brier(
            role_probs,
            ROLE_LABELS,
            observation.actual_role,
        )
        role_match = role_choice == observation.actual_role
        scores.append(role_brier)

    risk_brier: float | None = None
    risk_match: bool | None = None
    if observation.actual_risk is not None:
        risk_brier = _categorical_brier(
            risk_probs,
            RISK_LABELS,
            observation.actual_risk,
        )
        risk_match = risk_choice == observation.actual_risk
        scores.append(risk_brier)

    system2_brier: float | None = None
    if observation.system2_needed is not None:
        system2_brier = _binary_brier(system2_p, observation.system2_needed)
        scores.append(system2_brier)

    verification_brier: float | None = None
    if observation.verification_needed is not None:
        verification_brier = _binary_brier(
            verification_p,
            observation.verification_needed,
        )
        scores.append(verification_brier)

    mean_brier = None
    if scores:
        mean_brier = round(sum(scores) / len(scores), 9)

    return ProviderCalibration(
        provider=provider,
        model=model,
        role_scored=observation.actual_role is not None,
        role_match=role_match,
        role_brier=role_brier,
        risk_scored=observation.actual_risk is not None,
        risk_match=risk_match,
        risk_brier=risk_brier,
        system2_scored=observation.system2_needed is not None,
        system2_brier=system2_brier,
        verification_scored=observation.verification_needed is not None,
        verification_brier=verification_brier,
        scored_dimensions=len(scores),
        mean_brier=mean_brier,
    )


def _validate_dispatch_shadow(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != "phios.reflex_dispatch_shadow_receipt.v0.2":
        raise ReflexOutcomeContractError("unsupported dispatch shadow schema")
    if payload.get("planner_influenced_by_reflex") is not False:
        raise ReflexOutcomeContractError(
            "calibration requires an uninfluenced shadow dispatch"
        )
    if payload.get("operational_context_contains_reflex") is not False:
        raise ReflexOutcomeContractError("dispatch context was contaminated")
    if payload.get("operational_plan_contains_reflex") is not False:
        raise ReflexOutcomeContractError("dispatch plan was contaminated")
    if payload.get("action_authority") is not False:
        raise ReflexOutcomeContractError("shadow receipt cannot carry action authority")
    if payload.get("execution_authority") is not False:
        raise ReflexOutcomeContractError(
            "shadow receipt cannot carry execution authority"
        )
    for label in (
        "task_sha256",
        "operational_context_sha256",
        "operational_plan_sha256",
        "receipt_sha256",
    ):
        _require_sha256(str(payload.get(label, "")), label)

    receipt_sha = str(payload["receipt_sha256"])
    without_receipt = dict(payload)
    without_receipt.pop("receipt_sha256", None)
    if _digest(without_receipt) != receipt_sha:
        raise ReflexOutcomeContractError(
            "dispatch shadow receipt hash does not match contents"
        )

    reflex = _mapping(payload.get("reflex_receipt"), "reflex_receipt")
    if reflex.get("schema") != "phios.reflex_shadow_receipt.v0.1":
        raise ReflexOutcomeContractError("unsupported nested reflex schema")
    if reflex.get("action_authority") is not False:
        raise ReflexOutcomeContractError("nested reflex cannot carry action authority")
    if reflex.get("execution_authority") is not False:
        raise ReflexOutcomeContractError(
            "nested reflex cannot carry execution authority"
        )
    _require_sha256(str(reflex.get("input_sha256", "")), "reflex input_sha256")
    _require_sha256(str(reflex.get("receipt_sha256", "")), "reflex receipt_sha256")
    reflex_without_receipt = dict(reflex)
    reflex_receipt_sha = str(reflex_without_receipt.pop("receipt_sha256"))
    if _digest(reflex_without_receipt) != reflex_receipt_sha:
        raise ReflexOutcomeContractError(
            "nested reflex receipt hash does not match contents"
        )


def _distribution(
    raw: object,
    labels: tuple[str, ...],
    name: str,
) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != set(labels):
        raise ReflexOutcomeContractError(f"{name} labels are invalid")
    values = {label: _probability(raw[label], f"{name}.{label}") for label in labels}
    if abs(sum(values.values()) - 1.0) > 1e-6:
        raise ReflexOutcomeContractError(f"{name} must sum to 1")
    return values


def _categorical_brier(
    probabilities: Mapping[str, float],
    labels: tuple[str, ...],
    actual: str,
) -> float:
    score = sum(
        (probabilities[label] - (1.0 if label == actual else 0.0)) ** 2
        for label in labels
    ) / len(labels)
    return round(score, 9)


def _binary_brier(probability: float, actual: bool) -> float:
    return round((probability - (1.0 if actual else 0.0)) ** 2, 9)


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool):
        number = float(int(value))
    elif isinstance(value, (int, float, str)):
        try:
            number = float(value)
        except ValueError as exc:
            raise ReflexOutcomeContractError(
                f"{label} must be numeric"
            ) from exc
    else:
        raise ReflexOutcomeContractError(f"{label} must be numeric")
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ReflexOutcomeContractError(f"{label} must be in [0, 1]")
    return number


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReflexOutcomeContractError(f"{label} must be an object")
    return dict(value)


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexOutcomeContractError(f"{label} must be a SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexOutcomeContractError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc


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
        raise ReflexOutcomeContractError(
            "calibration payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
