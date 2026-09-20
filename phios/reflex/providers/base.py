"""PhiReflex provider contract."""

from __future__ import annotations

from typing import Protocol

from phios.reflex.models import ReflexDecision, ReflexInput


class ReflexProviderUnavailable(RuntimeError):
    """Provider cannot currently evaluate the request."""


class ReflexProvider(Protocol):
    name: str

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        """Return a bounded advisory decision with zero authority."""
