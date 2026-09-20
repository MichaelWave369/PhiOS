"""Deterministic local PhiReflex baseline provider."""

from __future__ import annotations

from phios.reflex.models import (
    ROLE_LABELS,
    RISK_LABELS,
    ReflexDecision,
    ReflexInput,
    confidence_for,
    normalized_distribution,
)


class RulesReflexProvider:
    name = "rules"

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        text = reflex_input.task_text.strip().lower()
        role = self._role(text)
        risk = (
            "high"
            if reflex_input.external_side_effect
            else "elevated"
            if reflex_input.tool_intent
            else "low"
        )
        role_probs = self._peaked(role, ROLE_LABELS, 0.84)
        risk_probs = self._peaked(risk, RISK_LABELS, 0.90)
        complex_terms = (
            "design",
            "debug",
            "research",
            "compare",
            "architecture",
            "why",
            "reason",
            "analyze",
            "analyse",
        )
        needs_system2 = 0.88 if len(text) > 220 or any(x in text for x in complex_terms) else 0.32
        needs_verification = (
            0.96
            if reflex_input.external_side_effect
            else 0.76
            if reflex_input.tool_intent
            else 0.40
        )
        return ReflexDecision(
            provider=self.name,
            provider_version="0.1.0",
            model="deterministic-rules",
            role=role,
            role_probabilities=role_probs,
            risk=risk,
            risk_probabilities=risk_probs,
            needs_system2_probability=needs_system2,
            needs_verification_probability=needs_verification,
            confidence=min(confidence_for(role_probs), confidence_for(risk_probs)),
            latency_ms=0.0,
        )

    @staticmethod
    def _role(text: str) -> str:
        if any(word in text for word in ("translate", "translation", "localize", "localise")):
            return "translator"
        if any(word in text for word in ("ledger", "audit", "receipt", "provenance")):
            return "ledger"
        if any(word in text for word in ("build", "code", "implement", "patch", "repo", "program")):
            return "builder"
        if any(word in text for word in ("summarize", "summarise", "synthesize", "synthesise", "combine")):
            return "synthesis"
        return "utility"

    @staticmethod
    def _peaked(
        selected: str,
        labels: tuple[str, ...],
        peak: float,
    ) -> tuple[tuple[str, float], ...]:
        remainder = (1.0 - peak) / (len(labels) - 1)
        values = {
            label: peak if label == selected else remainder
            for label in labels
        }
        return normalized_distribution(values, labels)
