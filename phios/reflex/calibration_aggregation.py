"""PhiReflex v0.4 calibration aggregation and promotion-readiness evidence.

Aggregates validated v0.3 calibration receipts without granting routing or
promotion authority. One run contributes at most one distinct calibration
receipt to a report; conflicting receipts for the same run are excluded.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ReflexAggregationContractError(ValueError):
    """Raised when aggregate calibration evidence is malformed."""


DIMENSIONS = ("role", "risk", "system2", "verification")


@dataclass(frozen=True, slots=True)
class PromotionReadinessPolicy:
    policy_id: str
    candidate_provider: str
    min_unique_runs: int = 20
    min_candidate_scored_runs: int = 12
    min_dimension_coverage: float = 0.50
    min_shadow_availability_rate: float = 0.80
    max_candidate_mean_brier: float = 0.20
    max_regression_vs_paired_baseline: float = 0.02

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ReflexAggregationContractError("policy_id must be non-empty")
        if not self.candidate_provider.strip():
            raise ReflexAggregationContractError(
                "candidate_provider must be non-empty"
            )
        for int_label, int_value in (
            ("min_unique_runs", self.min_unique_runs),
            ("min_candidate_scored_runs", self.min_candidate_scored_runs),
        ):
            if (
                isinstance(int_value, bool)
                or not isinstance(int_value, int)
                or int_value < 1
            ):
                raise ReflexAggregationContractError(
                    f"{int_label} must be a positive integer"
                )
        for float_label, float_value in (
            ("min_dimension_coverage", self.min_dimension_coverage),
            ("min_shadow_availability_rate", self.min_shadow_availability_rate),
            ("max_candidate_mean_brier", self.max_candidate_mean_brier),
            (
                "max_regression_vs_paired_baseline",
                self.max_regression_vs_paired_baseline,
            ),
        ):
            _require_finite(float_value, float_label)
        if not 0 <= self.min_dimension_coverage <= 1:
            raise ReflexAggregationContractError(
                "min_dimension_coverage must be in [0, 1]"
            )
        if not 0 <= self.min_shadow_availability_rate <= 1:
            raise ReflexAggregationContractError(
                "min_shadow_availability_rate must be in [0, 1]"
            )
        if self.max_candidate_mean_brier < 0:
            raise ReflexAggregationContractError(
                "max_candidate_mean_brier must be non-negative"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "candidate_provider": self.candidate_provider,
            "min_unique_runs": self.min_unique_runs,
            "min_candidate_scored_runs": self.min_candidate_scored_runs,
            "min_dimension_coverage": self.min_dimension_coverage,
            "min_shadow_availability_rate": self.min_shadow_availability_rate,
            "max_candidate_mean_brier": self.max_candidate_mean_brier,
            "max_regression_vs_paired_baseline": (
                self.max_regression_vs_paired_baseline
            ),
        }

    @property
    def policy_sha256(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class ProviderAggregate:
    provider: str
    models: tuple[str, ...]
    available_runs: int
    scored_runs: int
    scored_dimension_observations: int
    dimension_counts: tuple[tuple[str, int], ...]
    dimension_mean_brier: tuple[tuple[str, float | None], ...]
    dimension_coverage: float
    mean_brier: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "models": list(self.models),
            "available_runs": self.available_runs,
            "scored_runs": self.scored_runs,
            "scored_dimension_observations": self.scored_dimension_observations,
            "dimension_counts": dict(self.dimension_counts),
            "dimension_mean_brier": dict(self.dimension_mean_brier),
            "dimension_coverage": self.dimension_coverage,
            "mean_brier": self.mean_brier,
        }


@dataclass(frozen=True, slots=True)
class PromotionReadinessReceipt:
    schema: str
    status: str
    reason: str
    policy_id: str
    policy_sha256: str
    candidate_provider: str
    unique_runs_seen: int
    included_runs: int
    ambiguous_runs: tuple[str, ...]
    exact_duplicates_ignored: int
    shadow_ok_runs: int
    shadow_unavailable_runs: int
    shadow_error_runs: int
    shadow_availability_rate: float
    baseline: ProviderAggregate
    candidate: ProviderAggregate | None
    paired_baseline: ProviderAggregate | None
    candidate_vs_paired_baseline_delta: float | None
    source_receipt_sha256s: tuple[str, ...]
    thresholds_passed: tuple[tuple[str, bool], ...]
    routing_influence_authority: bool
    promotion_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "candidate_provider": self.candidate_provider,
            "unique_runs_seen": self.unique_runs_seen,
            "included_runs": self.included_runs,
            "ambiguous_runs": list(self.ambiguous_runs),
            "exact_duplicates_ignored": self.exact_duplicates_ignored,
            "shadow_ok_runs": self.shadow_ok_runs,
            "shadow_unavailable_runs": self.shadow_unavailable_runs,
            "shadow_error_runs": self.shadow_error_runs,
            "shadow_availability_rate": self.shadow_availability_rate,
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "paired_baseline": (
                self.paired_baseline.to_dict() if self.paired_baseline else None
            ),
            "candidate_vs_paired_baseline_delta": (
                self.candidate_vs_paired_baseline_delta
            ),
            "source_receipt_sha256s": list(self.source_receipt_sha256s),
            "thresholds_passed": dict(self.thresholds_passed),
            "routing_influence_authority": self.routing_influence_authority,
            "promotion_authority": self.promotion_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


def aggregate_calibration_receipts(
    receipts: Iterable[Mapping[str, Any]],
    *,
    policy: PromotionReadinessPolicy,
) -> PromotionReadinessReceipt:
    """Aggregate unique-run v0.3 evidence under an explicit advisory policy."""

    validated = [_validate_receipt(dict(item)) for item in receipts]
    by_run: dict[str, dict[str, dict[str, Any]]] = {}
    exact_duplicates = 0
    for receipt in validated:
        run_id = str(receipt["run_id"])
        receipt_sha = str(receipt["receipt_sha256"])
        run_receipts = by_run.setdefault(run_id, {})
        if receipt_sha in run_receipts:
            exact_duplicates += 1
            continue
        run_receipts[receipt_sha] = receipt

    ambiguous_runs = tuple(
        sorted(run_id for run_id, items in by_run.items() if len(items) > 1)
    )
    included = [
        next(iter(items.values()))
        for run_id, items in sorted(by_run.items())
        if run_id not in ambiguous_runs
    ]

    baseline_rows = [dict(item["baseline"]) for item in included]
    baseline = _aggregate_provider_rows(baseline_rows)

    shadow_ok = sum(1 for item in included if item["shadow_status"] == "ok")
    shadow_unavailable = sum(
        1 for item in included if item["shadow_status"] == "unavailable"
    )
    shadow_error = sum(1 for item in included if item["shadow_status"] == "error")
    availability_rate = (
        round(shadow_ok / len(included), 9) if included else 0.0
    )

    candidate_rows: list[dict[str, Any]] = []
    paired_baseline_rows: list[dict[str, Any]] = []
    for item in included:
        shadow_obj = item.get("shadow")
        if not isinstance(shadow_obj, dict):
            continue
        if str(shadow_obj.get("provider", "")) != policy.candidate_provider:
            continue
        candidate_rows.append(dict(shadow_obj))
        paired_baseline_rows.append(dict(item["baseline"]))

    candidate = (
        _aggregate_provider_rows(candidate_rows) if candidate_rows else None
    )
    paired_baseline = (
        _aggregate_provider_rows(paired_baseline_rows)
        if paired_baseline_rows
        else None
    )

    delta: float | None = None
    if (
        candidate is not None
        and paired_baseline is not None
        and candidate.mean_brier is not None
        and paired_baseline.mean_brier is not None
    ):
        delta = round(candidate.mean_brier - paired_baseline.mean_brier, 9)

    threshold_map = _thresholds(
        policy=policy,
        unique_runs_seen=len(by_run),
        included_runs=len(included),
        shadow_availability_rate=availability_rate,
        candidate=candidate,
        delta=delta,
    )
    status, reason = _readiness_status(
        threshold_map=threshold_map,
        candidate=candidate,
    )

    source_shas = tuple(
        sorted(str(item["receipt_sha256"]) for item in included)
    )
    thresholds = tuple(sorted(threshold_map.items()))
    payload: dict[str, object] = {
        "schema": "phios.reflex_promotion_readiness_receipt.v0.4",
        "status": status,
        "reason": reason,
        "policy_id": policy.policy_id,
        "policy_sha256": policy.policy_sha256,
        "candidate_provider": policy.candidate_provider,
        "unique_runs_seen": len(by_run),
        "included_runs": len(included),
        "ambiguous_runs": list(ambiguous_runs),
        "exact_duplicates_ignored": exact_duplicates,
        "shadow_ok_runs": shadow_ok,
        "shadow_unavailable_runs": shadow_unavailable,
        "shadow_error_runs": shadow_error,
        "shadow_availability_rate": availability_rate,
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict() if candidate else None,
        "paired_baseline": (
            paired_baseline.to_dict() if paired_baseline else None
        ),
        "candidate_vs_paired_baseline_delta": delta,
        "source_receipt_sha256s": list(source_shas),
        "thresholds_passed": dict(thresholds),
        "routing_influence_authority": False,
        "promotion_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    return PromotionReadinessReceipt(
        schema="phios.reflex_promotion_readiness_receipt.v0.4",
        status=status,
        reason=reason,
        policy_id=policy.policy_id,
        policy_sha256=policy.policy_sha256,
        candidate_provider=policy.candidate_provider,
        unique_runs_seen=len(by_run),
        included_runs=len(included),
        ambiguous_runs=ambiguous_runs,
        exact_duplicates_ignored=exact_duplicates,
        shadow_ok_runs=shadow_ok,
        shadow_unavailable_runs=shadow_unavailable,
        shadow_error_runs=shadow_error,
        shadow_availability_rate=availability_rate,
        baseline=baseline,
        candidate=candidate,
        paired_baseline=paired_baseline,
        candidate_vs_paired_baseline_delta=delta,
        source_receipt_sha256s=source_shas,
        thresholds_passed=thresholds,
        routing_influence_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        receipt_sha256=_digest(payload),
    )


def default_jev_readiness_policy() -> PromotionReadinessPolicy:
    return PromotionReadinessPolicy(
        policy_id="phios.reflex.jev.shadow-readiness.v0.4",
        candidate_provider="jev",
    )


def _thresholds(
    *,
    policy: PromotionReadinessPolicy,
    unique_runs_seen: int,
    included_runs: int,
    shadow_availability_rate: float,
    candidate: ProviderAggregate | None,
    delta: float | None,
) -> dict[str, bool]:
    candidate_scored_runs = candidate.scored_runs if candidate else 0
    coverage = candidate.dimension_coverage if candidate else 0.0
    mean_brier = candidate.mean_brier if candidate else None
    return {
        "minimum_unique_runs": unique_runs_seen >= policy.min_unique_runs,
        "no_ambiguous_run_loss": included_runs == unique_runs_seen,
        "minimum_candidate_scored_runs": (
            candidate_scored_runs >= policy.min_candidate_scored_runs
        ),
        "minimum_dimension_coverage": (
            coverage >= policy.min_dimension_coverage
        ),
        "minimum_shadow_availability_rate": (
            shadow_availability_rate >= policy.min_shadow_availability_rate
        ),
        "maximum_candidate_mean_brier": (
            mean_brier is not None
            and mean_brier <= policy.max_candidate_mean_brier
        ),
        "maximum_regression_vs_paired_baseline": (
            delta is not None
            and delta <= policy.max_regression_vs_paired_baseline
        ),
    }


def _readiness_status(
    *,
    threshold_map: Mapping[str, bool],
    candidate: ProviderAggregate | None,
) -> tuple[str, str]:
    evidence_keys = (
        "minimum_unique_runs",
        "no_ambiguous_run_loss",
        "minimum_candidate_scored_runs",
        "minimum_dimension_coverage",
        "minimum_shadow_availability_rate",
    )
    if candidate is None or not all(threshold_map[key] for key in evidence_keys):
        return "INSUFFICIENT_EVIDENCE", "evidence_thresholds_not_met"
    quality_keys = (
        "maximum_candidate_mean_brier",
        "maximum_regression_vs_paired_baseline",
    )
    if not all(threshold_map[key] for key in quality_keys):
        return "NOT_REVIEW_ELIGIBLE", "quality_thresholds_not_met"
    return "REVIEW_ELIGIBLE", "all_advisory_review_thresholds_met"


def _aggregate_provider_rows(
    rows: list[dict[str, Any]],
) -> ProviderAggregate:
    if not rows:
        return ProviderAggregate(
            provider="none",
            models=(),
            available_runs=0,
            scored_runs=0,
            scored_dimension_observations=0,
            dimension_counts=tuple((name, 0) for name in DIMENSIONS),
            dimension_mean_brier=tuple((name, None) for name in DIMENSIONS),
            dimension_coverage=0.0,
            mean_brier=None,
        )

    providers = {str(row.get("provider", "")).strip() for row in rows}
    if "" in providers or len(providers) != 1:
        raise ReflexAggregationContractError(
            "provider aggregate rows must share one provider identity"
        )
    provider = next(iter(providers))
    models = tuple(sorted({str(row.get("model", "")).strip() for row in rows}))
    if any(not item for item in models):
        raise ReflexAggregationContractError("provider model must be non-empty")

    values: dict[str, list[float]] = {name: [] for name in DIMENSIONS}
    scored_runs = 0
    total_dimension_scores: list[float] = []
    for row in rows:
        scored_this_run = False
        for dimension in DIMENSIONS:
            scored_key = f"{dimension}_scored"
            brier_key = f"{dimension}_brier"
            scored = row.get(scored_key)
            brier = row.get(brier_key)
            if scored is True:
                value = _require_brier(brier, brier_key)
                values[dimension].append(value)
                total_dimension_scores.append(value)
                scored_this_run = True
            elif scored is not False:
                raise ReflexAggregationContractError(
                    f"{scored_key} must be boolean"
                )
            elif brier is not None:
                raise ReflexAggregationContractError(
                    f"{brier_key} must be null when unscored"
                )
        declared_count = row.get("scored_dimensions")
        if (
            isinstance(declared_count, bool)
            or not isinstance(declared_count, int)
            or declared_count != sum(
                1 for dimension in DIMENSIONS if row[f"{dimension}_scored"]
            )
        ):
            raise ReflexAggregationContractError(
                "provider scored_dimensions does not match dimension flags"
            )
        if scored_this_run:
            scored_runs += 1

    counts = tuple((name, len(values[name])) for name in DIMENSIONS)
    means = tuple(
        (
            name,
            round(sum(values[name]) / len(values[name]), 9)
            if values[name]
            else None,
        )
        for name in DIMENSIONS
    )
    possible = len(rows) * len(DIMENSIONS)
    observed = len(total_dimension_scores)
    coverage = round(observed / possible, 9) if possible else 0.0
    mean_brier = (
        round(sum(total_dimension_scores) / observed, 9)
        if observed
        else None
    )
    return ProviderAggregate(
        provider=provider,
        models=models,
        available_runs=len(rows),
        scored_runs=scored_runs,
        scored_dimension_observations=observed,
        dimension_counts=counts,
        dimension_mean_brier=means,
        dimension_coverage=coverage,
        mean_brier=mean_brier,
    )


def _validate_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "phios.reflex_calibration_receipt.v0.3":
        raise ReflexAggregationContractError(
            "unsupported calibration receipt schema"
        )
    if payload.get("status") not in {
        "scored",
        "unscored_no_observed_labels",
    }:
        raise ReflexAggregationContractError(
            "unsupported calibration receipt status"
        )
    if payload.get("action_authority") is not False:
        raise ReflexAggregationContractError(
            "calibration receipt cannot carry action authority"
        )
    if payload.get("execution_authority") is not False:
        raise ReflexAggregationContractError(
            "calibration receipt cannot carry execution authority"
        )
    if not str(payload.get("run_id", "")).strip():
        raise ReflexAggregationContractError("run_id must be non-empty")
    for label in (
        "dispatch_shadow_receipt_sha256",
        "operational_context_sha256",
        "operational_plan_sha256",
        "receipt_sha256",
    ):
        _require_sha256(str(payload.get(label, "")), label)
    if payload.get("shadow_status") not in {"ok", "unavailable", "error"}:
        raise ReflexAggregationContractError("invalid shadow_status")
    if payload.get("shadow_status") == "ok":
        if not isinstance(payload.get("shadow"), dict):
            raise ReflexAggregationContractError(
                "ok shadow status requires shadow calibration"
            )
    elif payload.get("shadow") is not None:
        raise ReflexAggregationContractError(
            "non-ok shadow status cannot carry shadow calibration"
        )
    if not isinstance(payload.get("baseline"), dict):
        raise ReflexAggregationContractError("baseline must be an object")
    if not isinstance(payload.get("observation"), dict):
        raise ReflexAggregationContractError("observation must be an object")
    if payload.get("compared_providers") is not (
        payload.get("shadow_status") == "ok"
    ):
        raise ReflexAggregationContractError(
            "compared_providers does not match shadow status"
        )

    expected = dict(payload)
    receipt_sha = str(expected.pop("receipt_sha256"))
    if _digest(expected) != receipt_sha:
        raise ReflexAggregationContractError(
            "calibration receipt hash does not match contents"
        )

    _aggregate_provider_rows([dict(payload["baseline"])])
    shadow_obj = payload.get("shadow")
    if isinstance(shadow_obj, dict):
        _aggregate_provider_rows([dict(shadow_obj)])
    return payload


def _require_brier(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReflexAggregationContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ReflexAggregationContractError(
            f"{label} must be finite and non-negative"
        )
    return number


def _require_finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReflexAggregationContractError(f"{label} must be finite")
    return number


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexAggregationContractError(
            f"{label} must be a SHA-256 hex digest"
        )
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexAggregationContractError(
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
        raise ReflexAggregationContractError(
            "aggregation payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
