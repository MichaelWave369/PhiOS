"""Optional TypeSafe Jev provider for PhiReflex shadow evaluation."""

from __future__ import annotations

import importlib
import os
import time
from collections.abc import Callable
from typing import Any

from phios.reflex.models import (
    ROLE_LABELS,
    RISK_LABELS,
    ReflexContractError,
    ReflexDecision,
    ReflexInput,
    confidence_for,
    normalized_distribution,
)
from phios.reflex.providers.base import ReflexProviderUnavailable


class JevReflexProvider:
    name = "jev"

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] | None = None,
        choice_factory: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._client_factory = client_factory
        self._choice_factory = choice_factory
        self._clock = clock

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        client_factory, choice_factory = self._resolve_sdk()
        questions = {
            "role": choice_factory(
                instructions="Which PhiOS advisory role best matches this task?",
                criteria={
                    "utility": "Small bounded utility or lookup task.",
                    "builder": "Software construction, editing, implementation, or debugging.",
                    "synthesis": "Combine, summarize, reconcile, or integrate information.",
                    "translator": "Translate or transform between languages/representations.",
                    "ledger": "Audit, provenance, receipt, verification-history, or recordkeeping.",
                },
            ),
            "risk": choice_factory(
                instructions="What advisory risk level best fits this task context?",
                criteria={
                    "low": "No external side effect and no tool use is implied.",
                    "elevated": "Tool use or consequential workflow interaction is implied.",
                    "high": "An external side effect is explicitly requested or expected.",
                },
            ),
            "needs_system2": choice_factory(
                instructions="Does this task need deliberative System Two reasoning?",
                criteria={
                    "yes": "Open-ended reasoning, research, architecture, debugging, or synthesis is needed.",
                    "no": "A fast bounded judgment or deterministic utility is sufficient.",
                },
            ),
            "needs_verification": choice_factory(
                instructions="Should downstream PhiOS verification be strongly preferred?",
                criteria={
                    "yes": "The task uses tools, external state, consequential claims, or side effects.",
                    "no": "The task is low-impact and self-contained.",
                },
            ),
        }
        state = reflex_input.to_dict()
        start = self._clock()
        try:
            client = client_factory()
            if hasattr(client, "__enter__"):
                with client as active:
                    response = active.system_one(state=state, questions=questions)
            else:
                response = client.system_one(state=state, questions=questions)
        except Exception as exc:
            raise ReflexProviderUnavailable(
                f"Jev evaluation failed: {type(exc).__name__}"
            ) from exc
        latency_ms = max(0.0, (self._clock() - start) * 1000.0)

        role_answer = self._answer(response, "role")
        risk_answer = self._answer(response, "risk")
        sys2_answer = self._answer(response, "needs_system2")
        verify_answer = self._answer(response, "needs_verification")

        role_probs = self._probabilities(role_answer, ROLE_LABELS)
        risk_probs = self._probabilities(risk_answer, RISK_LABELS)
        sys2_probs = self._probabilities(sys2_answer, ("yes", "no"))
        verify_probs = self._probabilities(verify_answer, ("yes", "no"))
        role = str(getattr(role_answer, "choice", "")).strip()
        risk = str(getattr(risk_answer, "choice", "")).strip()
        if role not in ROLE_LABELS or risk not in RISK_LABELS:
            raise ReflexProviderUnavailable("Jev returned an unsupported PhiReflex label")

        model = str(getattr(response, "model", "jev-latest") or "jev-latest")
        confidence = min(confidence_for(role_probs), confidence_for(risk_probs))
        return ReflexDecision(
            provider=self.name,
            provider_version="typesafe-sdk-0.7.x",
            model=model,
            role=role,
            role_probabilities=role_probs,
            risk=risk,
            risk_probabilities=risk_probs,
            needs_system2_probability=dict(sys2_probs)["yes"],
            needs_verification_probability=dict(verify_probs)["yes"],
            confidence=confidence,
            latency_ms=round(latency_ms, 3),
        )

    def _resolve_sdk(
        self,
    ) -> tuple[Callable[[], Any], Callable[..., Any]]:
        if self._client_factory is not None and self._choice_factory is not None:
            return self._client_factory, self._choice_factory
        if not os.getenv("TYPESAFE_API_KEY"):
            raise ReflexProviderUnavailable("TYPESAFE_API_KEY is not configured")
        try:
            sdk = importlib.import_module("typesafe_sdk")
        except ImportError as exc:
            raise ReflexProviderUnavailable(
                "typesafe-sdk is not installed; install PhiOS with [reflex-jev]"
            ) from exc
        client_factory = getattr(sdk, "TypeSafeClient", None)
        choice_factory = getattr(sdk, "Choice", None)
        if client_factory is None or choice_factory is None:
            raise ReflexProviderUnavailable("unsupported typesafe-sdk API")
        return client_factory, choice_factory

    @staticmethod
    def _answer(response: Any, name: str) -> Any:
        container = getattr(response, "choices", None)
        if container is None:
            container = getattr(response, "answers", None)
        if container is None or name not in container:
            raise ReflexProviderUnavailable(f"Jev response omitted {name!r}")
        return container[name]

    @staticmethod
    def _probabilities(
        answer: Any,
        labels: tuple[str, ...],
    ) -> tuple[tuple[str, float], ...]:
        raw = getattr(answer, "probabilities", None)
        if isinstance(raw, dict):
            try:
                return normalized_distribution(
                    {label: float(raw[label]) for label in labels},
                    labels,
                )
            except (KeyError, TypeError, ValueError, ReflexContractError) as exc:
                raise ReflexProviderUnavailable(
                    "Jev returned invalid probabilities"
                ) from exc
        choice = str(getattr(answer, "choice", "")).strip()
        if choice not in labels:
            raise ReflexProviderUnavailable("Jev returned no usable probability distribution")
        return normalized_distribution(
            {label: 1.0 if label == choice else 0.0 for label in labels},
            labels,
        )
