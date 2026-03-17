from __future__ import annotations

import json

from phios.core.kernel_rollout import (
    KernelRolloutStore,
    build_rollout_review,
    export_compare_report,
    export_review_markdown,
    record_compare_result,
    summarize_compare_records,
)


def _runtime_payload() -> dict[str, object]:
    return {
        "enabled": True,
        "compare_mode": True,
        "configured_adapter": "legacy",
        "shadow_adapter": "tiekat_v50",
        "primary": {
            "adapter": "legacy",
            "mode": "primary",
            "verdict": "proceed",
            "recommendation": "continue",
            "coherence_score": 0.8,
            "stability_score": 0.7,
            "readiness_score": 0.75,
            "risk_score": 0.2,
            "null_result": False,
        },
        "shadow": {
            "adapter": "tiekat_v50",
            "mode": "shadow",
            "verdict": "hold",
            "recommendation": "pause",
            "coherence_score": 0.5,
            "stability_score": 0.6,
            "readiness_score": 0.6,
            "risk_score": 0.4,
            "null_result": False,
        },
        "deltas": {
            "verdict_changed": True,
            "recommendation_changed": True,
            "coherence_delta": 0.3,
            "stability_delta": 0.1,
            "readiness_delta": 0.15,
            "risk_delta": -0.2,
        },
    }


def test_compare_record_persistence_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIOS_KERNEL_COMPARE_DEDUPE_SECONDS", "3600")
    store = KernelRolloutStore(root=tmp_path)
    runtime = _runtime_payload()

    first = record_compare_result(runtime, context_type="status", source_label="phi status", store=store)
    second = record_compare_result(runtime, context_type="status", source_label="phi status", store=store)

    assert first is not None
    assert second is None
    rows = store.read_records()
    assert len(rows) == 1
    assert rows[0]["primary_adapter"] == "legacy"


def test_compare_summary_and_export_shape(tmp_path):
    store = KernelRolloutStore(root=tmp_path)
    record = record_compare_result(_runtime_payload(), context_type="eval", source_label="case-a", store=store)
    assert record is not None
    records = store.query_records(adapter="legacy", context_type="eval")
    summary = summarize_compare_records(records)
    assert summary["total_cases"] == 1
    assert summary["verdict_changes"] == 1

    report_path = export_compare_report(str(tmp_path / "report.json"), records)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "summary" in data
    assert isinstance(data.get("records"), list)


def test_disabled_mode_noop_record(tmp_path):
    store = KernelRolloutStore(root=tmp_path)
    out = record_compare_result({"enabled": False}, context_type="status", source_label="phi status", store=store)
    assert out is None
    assert store.read_records() == []


def test_rollout_review_status_ready_and_hold(tmp_path):
    ready_records = []
    for i in range(6):
        ready_records.append(
            {
                "id": str(i),
                "verdict_changed": False,
                "recommendation_changed": False,
                "null_result_primary": False,
                "null_result_shadow": False,
                "score_delta_json": {"coherence_delta": 0.02, "stability_delta": 0.01, "readiness_delta": 0.02, "risk_delta": 0.01},
            }
        )
    ready = build_rollout_review(ready_records)
    assert ready["status"] == "ready"

    hold_records = []
    for i in range(8):
        hold_records.append(
            {
                "id": str(i),
                "verdict_changed": True,
                "recommendation_changed": True,
                "null_result_primary": i % 2 == 0,
                "null_result_shadow": False,
                "score_delta_json": {"coherence_delta": 0.5, "stability_delta": 0.1, "readiness_delta": 0.1, "risk_delta": 0.1},
            }
        )
    hold = build_rollout_review(hold_records)
    assert hold["status"] == "hold"
    assert "VERDICT_CHANGE_RATE_HIGH" in hold["reason_codes"]


def test_markdown_export_shape(tmp_path):
    review = build_rollout_review([])
    md = export_review_markdown(str(tmp_path / "review.md"), review)
    body = md.read_text(encoding="utf-8")
    assert body.startswith("# Kernel Rollout Review")
    assert "Promotion readiness" in body
    assert "advisory" in body.lower()
