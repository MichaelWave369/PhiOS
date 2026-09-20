"""PhiReflex v0.1 shadow-mode orchestration."""

from __future__ import annotations

from phios.reflex.models import ReflexInput, ReflexShadowReceipt, build_shadow_receipt
from phios.reflex.providers.base import ReflexProvider, ReflexProviderUnavailable
from phios.reflex.providers.rules import RulesReflexProvider


class PhiReflex:
    """Run a deterministic baseline and one optional provider in shadow mode."""

    def __init__(
        self,
        *,
        baseline: ReflexProvider | None = None,
        shadow: ReflexProvider | None = None,
    ) -> None:
        self._baseline = baseline or RulesReflexProvider()
        self._shadow = shadow

    def evaluate(self, reflex_input: ReflexInput) -> ReflexShadowReceipt:
        baseline = self._baseline.evaluate(reflex_input)
        if self._shadow is None:
            return build_shadow_receipt(
                reflex_input=reflex_input,
                baseline=baseline,
                shadow_status="unavailable",
                shadow=None,
                shadow_provider="none",
                shadow_reason="no shadow provider configured",
            )
        try:
            shadow = self._shadow.evaluate(reflex_input)
        except ReflexProviderUnavailable as exc:
            return build_shadow_receipt(
                reflex_input=reflex_input,
                baseline=baseline,
                shadow_status="unavailable",
                shadow=None,
                shadow_provider=self._shadow.name,
                shadow_reason=str(exc),
            )
        except Exception as exc:
            return build_shadow_receipt(
                reflex_input=reflex_input,
                baseline=baseline,
                shadow_status="error",
                shadow=None,
                shadow_provider=self._shadow.name,
                shadow_reason=type(exc).__name__,
            )
        return build_shadow_receipt(
            reflex_input=reflex_input,
            baseline=baseline,
            shadow_status="ok",
            shadow=shadow,
            shadow_provider=self._shadow.name,
            shadow_reason=None,
        )
