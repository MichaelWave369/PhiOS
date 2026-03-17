from __future__ import annotations

from phios.core.kernel_runtime import KernelRuntimeConfig, NormalizedKernelResult, run_kernel_runtime


class StubAdapter:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def runtime(self, *, prompt=None, adapter=None, mode=None):
        self.calls.append({"prompt": prompt, "adapter": adapter, "mode": mode})
        if mode == "shadow":
            return {
                "engine": "phik",
                "engine_version": "2.0",
                "substrate": "external",
                "substrate_version": "50",
                "adapter": adapter,
                "mode": mode,
                "verdict": "hold",
                "evidence_level": "medium",
                "coherence_score": 0.7,
                "stability_score": 0.8,
                "readiness_score": 0.6,
                "risk_score": 0.2,
                "null_result": False,
                "recommendation": "wait",
                "debug": {"path": "shadow"},
            }
        return {
            "engine": "phik",
            "engine_version": "2.0",
            "substrate": "external",
            "substrate_version": "50",
            "adapter": adapter,
            "mode": mode,
            "verdict": "proceed",
            "evidence_level": "high",
            "coherence_score": 0.9,
            "stability_score": 0.95,
            "readiness_score": 0.88,
            "risk_score": 0.1,
            "null_result": False,
            "recommendation": "continue",
            "debug": {"path": "primary"},
        }


def test_runtime_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PHIOS_KERNEL_ENABLED", raising=False)
    monkeypatch.delenv("PHIOS_KERNEL_ADAPTER", raising=False)

    cfg = KernelRuntimeConfig.from_env()
    assert cfg.enabled is False
    assert cfg.adapter == "legacy"

    adapter = StubAdapter()
    out = run_kernel_runtime(adapter)
    assert out["enabled"] is False
    assert adapter.calls == []


def test_runtime_explicit_tiekat_v50_path(monkeypatch):
    monkeypatch.setenv("PHIOS_KERNEL_ENABLED", "true")
    monkeypatch.setenv("PHIOS_KERNEL_ADAPTER", "tiekat_v50")

    adapter = StubAdapter()
    out = run_kernel_runtime(adapter, prompt="hello")

    assert out["enabled"] is True
    assert out["primary"]["adapter"] == "tiekat_v50"
    assert out["primary"]["substrate_version"] == "50"
    assert out["primary"]["verdict"] == "proceed"
    assert adapter.calls == [{"prompt": "hello", "adapter": "tiekat_v50", "mode": "primary"}]


def test_runtime_compare_shadow_mode(monkeypatch):
    monkeypatch.setenv("PHIOS_KERNEL_ENABLED", "true")
    monkeypatch.setenv("PHIOS_KERNEL_ADAPTER", "legacy")
    monkeypatch.setenv("PHIOS_KERNEL_SHADOW_ADAPTER", "tiekat_v50")
    monkeypatch.setenv("PHIOS_KERNEL_COMPARE_MODE", "true")

    adapter = StubAdapter()
    out = run_kernel_runtime(adapter, prompt="check")

    assert out["primary"]["adapter"] == "legacy"
    assert out["shadow"]["adapter"] == "tiekat_v50"
    assert out["deltas"]["verdict_changed"] is True
    assert out["deltas"]["coherence_delta"] == 0.2
    assert len(adapter.calls) == 2


def test_normalized_result_handling_type_coercion():
    result = NormalizedKernelResult.from_payload(
        {
            "adapter": "legacy",
            "substrate_version": 50,
            "coherence_score": "0.4",
            "stability_score": "bad",
            "readiness_score": 1,
            "risk_score": 0,
            "null_result": 0,
            "debug": "ignored",
        }
    )

    public = result.to_public_dict()
    assert public["adapter"] == "legacy"
    assert public["substrate_version"] == "50"
    assert public["coherence_score"] == 0.4
    assert public["stability_score"] is None
    assert public["readiness_score"] == 1.0
    assert public["risk_score"] == 0.0
    assert public["null_result"] is False
    assert public["debug"] == {}
