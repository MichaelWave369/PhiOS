"""PhiKernel normalized runtime contract integration for PhiOS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from phios.adapters.phik import PhiKernelCLIAdapter


_ALLOWED_ADAPTERS = {"legacy", "tiekat_v50"}


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class KernelRuntimeConfig:
    enabled: bool = False
    adapter: str = "legacy"
    shadow_adapter: str | None = None
    compare_mode: bool = False

    @classmethod
    def from_env(cls) -> "KernelRuntimeConfig":
        adapter = (os.getenv("PHIOS_KERNEL_ADAPTER") or "legacy").strip() or "legacy"
        shadow_adapter_raw = (os.getenv("PHIOS_KERNEL_SHADOW_ADAPTER") or "").strip()
        shadow_adapter = shadow_adapter_raw or None

        if adapter not in _ALLOWED_ADAPTERS:
            adapter = "legacy"
        if shadow_adapter and shadow_adapter not in _ALLOWED_ADAPTERS:
            shadow_adapter = None

        return cls(
            enabled=_parse_bool(os.getenv("PHIOS_KERNEL_ENABLED"), default=False),
            adapter=adapter,
            shadow_adapter=shadow_adapter,
            compare_mode=_parse_bool(os.getenv("PHIOS_KERNEL_COMPARE_MODE"), default=False),
        )


@dataclass(slots=True)
class NormalizedKernelResult:
    engine: str | None
    engine_version: str | None
    substrate: str | None
    substrate_version: str | None
    adapter: str | None
    mode: str | None
    verdict: str | None
    evidence_level: str | None
    coherence_score: float | None
    stability_score: float | None
    readiness_score: float | None
    risk_score: float | None
    null_result: bool
    recommendation: str | None
    debug: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "NormalizedKernelResult":
        return cls(
            engine=_as_text(payload.get("engine")),
            engine_version=_as_text(payload.get("engine_version")),
            substrate=_as_text(payload.get("substrate")),
            substrate_version=_as_text(payload.get("substrate_version")),
            adapter=_as_text(payload.get("adapter")),
            mode=_as_text(payload.get("mode")),
            verdict=_as_text(payload.get("verdict")),
            evidence_level=_as_text(payload.get("evidence_level")),
            coherence_score=_as_float(payload.get("coherence_score")),
            stability_score=_as_float(payload.get("stability_score")),
            readiness_score=_as_float(payload.get("readiness_score")),
            risk_score=_as_float(payload.get("risk_score")),
            null_result=bool(payload.get("null_result", False)),
            recommendation=_as_text(payload.get("recommendation")),
            debug=_as_dict(payload.get("debug")),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "substrate_version": self.substrate_version,
            "mode": self.mode,
            "verdict": self.verdict,
            "coherence_score": self.coherence_score,
            "stability_score": self.stability_score,
            "readiness_score": self.readiness_score,
            "risk_score": self.risk_score,
            "recommendation": self.recommendation,
            "null_result": self.null_result,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "substrate": self.substrate,
            "evidence_level": self.evidence_level,
            "debug": self.debug,
        }


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _score_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 6)


def _compute_compare_deltas(primary: NormalizedKernelResult, shadow: NormalizedKernelResult) -> dict[str, Any]:
    return {
        "verdict_changed": primary.verdict != shadow.verdict,
        "recommendation_changed": primary.recommendation != shadow.recommendation,
        "coherence_delta": _score_delta(primary.coherence_score, shadow.coherence_score),
        "stability_delta": _score_delta(primary.stability_score, shadow.stability_score),
        "readiness_delta": _score_delta(primary.readiness_score, shadow.readiness_score),
        "risk_delta": _score_delta(primary.risk_score, shadow.risk_score),
    }


def run_kernel_runtime(
    adapter: PhiKernelCLIAdapter,
    *,
    prompt: str | None = None,
    config: KernelRuntimeConfig | None = None,
    context_type: str = "runtime",
    source_label: str = "phios",
    rollout_store: object | None = None,
) -> dict[str, Any]:
    cfg = config or KernelRuntimeConfig.from_env()
    out: dict[str, Any] = {
        "enabled": cfg.enabled,
        "configured_adapter": cfg.adapter,
        "compare_mode": cfg.compare_mode,
        "shadow_adapter": cfg.shadow_adapter,
    }
    if not cfg.enabled:
        return out

    primary_payload = adapter.runtime(prompt=prompt, adapter=cfg.adapter, mode="primary")
    primary = NormalizedKernelResult.from_payload(primary_payload)
    out["primary"] = primary.to_public_dict()

    if cfg.compare_mode and cfg.shadow_adapter:
        shadow_payload = adapter.runtime(prompt=prompt, adapter=cfg.shadow_adapter, mode="shadow")
        shadow = NormalizedKernelResult.from_payload(shadow_payload)
        out["shadow"] = shadow.to_public_dict()
        out["deltas"] = _compute_compare_deltas(primary, shadow)
        try:
            from phios.core.kernel_rollout import record_compare_result

            compare_record = record_compare_result(
                out,
                context_type=context_type,
                source_label=source_label,
                store=rollout_store,
            )
            if compare_record is not None:
                out["compare_record"] = compare_record
        except Exception:
            pass

    return out
