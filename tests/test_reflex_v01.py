from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from phios.reflex import PhiReflex, ReflexContractError, ReflexInput
from phios.reflex.providers import (
    JevReflexProvider,
    ReflexProviderUnavailable,
    RulesReflexProvider,
)


class _FakeChoice:
    def __init__(self, *, instructions, criteria):
        self.instructions = instructions
        self.criteria = criteria


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def system_one(self, *, state, questions):
        assert state["task_text"]
        assert set(questions) == {
            "role",
            "risk",
            "needs_system2",
            "needs_verification",
        }
        return self._response


def _answer(choice: str, probabilities: dict[str, float]):
    return SimpleNamespace(choice=choice, probabilities=probabilities)


def _jev_response():
    return SimpleNamespace(
        model="jev-test",
        choices={
            "role": _answer(
                "builder",
                {
                    "utility": 0.02,
                    "builder": 0.90,
                    "synthesis": 0.04,
                    "translator": 0.01,
                    "ledger": 0.03,
                },
            ),
            "risk": _answer(
                "elevated",
                {"low": 0.08, "elevated": 0.88, "high": 0.04},
            ),
            "needs_system2": _answer(
                "yes",
                {"yes": 0.93, "no": 0.07},
            ),
            "needs_verification": _answer(
                "yes",
                {"yes": 0.81, "no": 0.19},
            ),
        },
    )


def test_rules_provider_is_deterministic_and_has_zero_authority():
    provider = RulesReflexProvider()
    item = ReflexInput(
        task_text="Build and test the PhiReflex provider in the repo",
        tool_intent=True,
    )

    first = provider.evaluate(item)
    second = provider.evaluate(item)

    assert first == second
    assert first.role == "builder"
    assert first.risk == "elevated"
    assert first.action_authority is False
    assert first.execution_authority is False


def test_jev_provider_maps_typed_probabilities_without_network():
    ticks = iter((100.0, 100.0125))
    provider = JevReflexProvider(
        client_factory=lambda: _FakeClient(_jev_response()),
        choice_factory=_FakeChoice,
        clock=lambda: next(ticks),
    )

    decision = provider.evaluate(
        ReflexInput(
            task_text="Build PhiReflex and inspect the repository",
            tool_intent=True,
        )
    )

    assert decision.provider == "jev"
    assert decision.model == "jev-test"
    assert decision.role == "builder"
    assert decision.risk == "elevated"
    assert decision.needs_system2_probability == pytest.approx(0.93)
    assert decision.needs_verification_probability == pytest.approx(0.81)
    assert decision.latency_ms == pytest.approx(12.5)
    assert decision.action_authority is False


def test_shadow_receipt_compares_rules_and_jev():
    ticks = iter((1.0, 1.005))
    shadow = JevReflexProvider(
        client_factory=lambda: _FakeClient(_jev_response()),
        choice_factory=_FakeChoice,
        clock=lambda: next(ticks),
    )

    receipt = PhiReflex(shadow=shadow).evaluate(
        ReflexInput(
            task_text="Build this provider and run tests",
            tool_intent=True,
        )
    )

    assert receipt.shadow_status == "ok"
    assert receipt.baseline.role == "builder"
    assert receipt.shadow is not None
    assert receipt.shadow.role == "builder"
    assert receipt.role_agreement is True
    assert receipt.risk_agreement is True
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert len(receipt.receipt_sha256) == 64


def test_missing_jev_key_is_receipted_as_unavailable(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    receipt = PhiReflex(shadow=JevReflexProvider()).evaluate(
        ReflexInput(task_text="Summarize this small note")
    )

    assert receipt.shadow_status == "unavailable"
    assert receipt.shadow is None
    assert receipt.shadow_provider == "jev"
    assert "TYPESAFE_API_KEY" in (receipt.shadow_reason or "")
    assert receipt.baseline.provider == "rules"


def test_provider_failure_is_receipted_without_breaking_baseline():
    class BrokenProvider:
        name = "broken"

        def evaluate(self, reflex_input):
            raise RuntimeError("boom")

    receipt = PhiReflex(shadow=BrokenProvider()).evaluate(
        ReflexInput(task_text="Build something")
    )

    assert receipt.baseline.role == "builder"
    assert receipt.shadow_status == "error"
    assert receipt.shadow_reason == "RuntimeError"


def test_rules_only_mode_is_explicitly_unavailable_shadow():
    receipt = PhiReflex().evaluate(
        ReflexInput(task_text="Translate this paragraph")
    )

    assert receipt.baseline.role == "translator"
    assert receipt.shadow_status == "unavailable"
    assert receipt.shadow_provider == "none"


def test_invalid_probability_contract_fails_closed():
    decision = RulesReflexProvider().evaluate(
        ReflexInput(task_text="Build this")
    )

    with pytest.raises(ReflexContractError):
        replace(
            decision,
            role_probabilities=(
                ("utility", 0.0),
                ("builder", 0.5),
                ("synthesis", 0.0),
                ("translator", 0.0),
                ("ledger", 0.0),
            ),
        )


def test_jev_sdk_failure_is_provider_unavailable():
    class FailingClient:
        def system_one(self, *, state, questions):
            raise TimeoutError("provider timeout")

    provider = JevReflexProvider(
        client_factory=FailingClient,
        choice_factory=_FakeChoice,
    )

    with pytest.raises(ReflexProviderUnavailable):
        provider.evaluate(ReflexInput(task_text="Build this"))
