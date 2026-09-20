import json
from pathlib import Path

import pytest

from phios.ledger_reports.observations import (
    ObservationReportService,
    ObservationSnapshotExporter,
)
from phios.mandala import AuthorityContext


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def _state(tmp_path: Path) -> Path:
    state_root = tmp_path / ".phios" / "spine-v0.1"
    state_root.mkdir(parents=True)
    return state_root


def _kernel_row() -> dict[str, object]:
    return {
        "id": "abc123",
        "created_at": "2026-09-20T20:00:00+00:00",
        "context_type": "runtime",
        "source_label": "SECRET_SOURCE_LABEL",
        "primary_adapter": "legacy",
        "shadow_adapter": "tiekat_v50",
        "primary_verdict": "pass",
        "shadow_verdict": "hold",
        "primary_mode": "primary",
        "shadow_mode": "shadow",
        "primary_coherence_score": 0.7,
        "shadow_coherence_score": 0.8,
        "primary_stability_score": 0.7,
        "shadow_stability_score": 0.8,
        "primary_readiness_score": 0.7,
        "shadow_readiness_score": 0.8,
        "primary_risk_score": 0.3,
        "shadow_risk_score": 0.2,
        "verdict_changed": True,
        "recommendation_changed": False,
        "score_delta_json": {
            "coherence_delta": -0.1,
            "stability_delta": -0.1,
            "readiness_delta": -0.1,
            "risk_delta": 0.1,
        },
        "null_result_primary": False,
        "null_result_shadow": False,
        "summary_note": "SECRET_SUMMARY",
        "raw_compare_json": {"debug": "SECRET_DEBUG"},
        "fingerprint": "a" * 64,
    }


def _run(run_id: str = "run_123456789abc") -> dict[str, object]:
    baseline = {
        "provider": "rules",
        "provider_version": "1",
        "model": "rules-v1",
        "role": "utility",
        "role_probabilities": {
            "utility": 1.0,
            "builder": 0.0,
            "synthesis": 0.0,
            "translator": 0.0,
            "ledger": 0.0,
        },
        "risk": "low",
        "risk_probabilities": {"low": 1.0, "elevated": 0.0, "high": 0.0},
        "needs_system2_probability": 0.1,
        "needs_verification_probability": 0.2,
        "confidence": 1.0,
        "latency_ms": 1.5,
        "action_authority": False,
        "execution_authority": False,
    }
    shadow = {
        **baseline,
        "provider": "jev",
        "model": "jev-test",
        "role": "builder",
        "confidence": 0.8,
        "latency_ms": 2.5,
    }
    reflex_receipt = {
        "schema": "phios.reflex_shadow_receipt.v0.1",
        "input_sha256": "b" * 64,
        "baseline": baseline,
        "shadow_status": "ok",
        "shadow": shadow,
        "shadow_provider": "jev",
        "shadow_reason": "SECRET_REASON",
        "role_agreement": False,
        "risk_agreement": True,
        "action_authority": False,
        "execution_authority": False,
        "receipt_sha256": "c" * 64,
    }
    dispatch_shadow = {
        "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
        "task_sha256": "d" * 64,
        "operational_context_sha256": "e" * 64,
        "operational_plan_sha256": "f" * 64,
        "reflex_receipt": reflex_receipt,
        "planner_influenced_by_reflex": False,
        "operational_context_contains_reflex": False,
        "operational_plan_contains_reflex": False,
        "action_authority": False,
        "execution_authority": False,
        "receipt_sha256": "1" * 64,
    }
    calibration = {
        "schema": "phios.reflex_calibration_receipt.v0.3",
        "status": "scored",
        "run_id": run_id,
        "dispatch_shadow_receipt_sha256": "1" * 64,
        "operational_context_sha256": "e" * 64,
        "operational_plan_sha256": "f" * 64,
        "observation": {
            "run_id": run_id,
            "dispatch_outcome": "succeeded",
            "observer_label": "SECRET_OBSERVER",
            "evidence_sha256": "2" * 64,
            "actual_role": "builder",
            "actual_risk": "low",
            "system2_needed": False,
            "verification_needed": True,
        },
        "baseline": {
            "provider": "rules",
            "model": "rules-v1",
            "role_scored": True,
            "role_match": False,
            "role_brier": 0.4,
            "risk_scored": True,
            "risk_match": True,
            "risk_brier": 0.0,
            "system2_scored": True,
            "system2_brier": 0.01,
            "verification_scored": True,
            "verification_brier": 0.64,
            "scored_dimensions": 4,
            "mean_brier": 0.2625,
        },
        "shadow_status": "ok",
        "shadow": {
            "provider": "jev",
            "model": "jev-test",
            "role_scored": True,
            "role_match": True,
            "role_brier": 0.1,
            "risk_scored": True,
            "risk_match": True,
            "risk_brier": 0.0,
            "system2_scored": True,
            "system2_brier": 0.02,
            "verification_scored": True,
            "verification_brier": 0.09,
            "scored_dimensions": 4,
            "mean_brier": 0.0525,
        },
        "compared_providers": True,
        "action_authority": False,
        "execution_authority": False,
        "receipt_sha256": "3" * 64,
    }
    return {
        "run_id": run_id,
        "task": "SECRET TASK TEXT",
        "status": "completed",
        "created_at": "2026-09-20T20:00:00+00:00",
        "updated_at": "2026-09-20T20:01:00+00:00",
        "stream_requested": True,
        "remote_run_id": "SECRET_REMOTE_ID",
        "remote_status": "completed",
        "context": {"secret": "SECRET_CONTEXT"},
        "plan": {
            "source": "agentception",
            "planner_available": True,
            "plan_steps": [{"secret": "SECRET_PLAN"}],
            "raw": {"token": "SECRET_TOKEN"},
        },
        "shadow_observations": {"phireflex_v0_2": dispatch_shadow},
        "reflex_calibration_receipts": [calibration],
        "reflex_activation_grant": {"secret": "SECRET_GRANT"},
        "outcome": "succeeded",
    }


def _write_sources(state_root: Path) -> None:
    phios_root = state_root.parent
    kernel = phios_root / "kernel_rollout" / "compare_records.jsonl"
    kernel.parent.mkdir(parents=True)
    kernel.write_text(json.dumps(_kernel_row()) + "\n", encoding="utf-8")
    runs = phios_root / "agents" / "runs"
    runs.mkdir(parents=True)
    run = _run()
    (runs / f"{run['run_id']}.json").write_text(json.dumps(run), encoding="utf-8")


def test_export_requires_permission_before_reading_sources(tmp_path: Path) -> None:
    state_root = _state(tmp_path)
    kernel = state_root.parent / "kernel_rollout" / "compare_records.jsonl"
    kernel.parent.mkdir(parents=True)
    kernel.write_text("{broken}\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="ledger.observation.export"):
        ObservationSnapshotExporter(state_root=state_root).export(authority=_authority())


def test_export_redacts_raw_dispatch_kernel_and_reflex_material(tmp_path: Path) -> None:
    state_root = _state(tmp_path)
    _write_sources(state_root)
    snapshot = ObservationSnapshotExporter(state_root=state_root).export(
        authority=_authority("ledger.observation.export")
    )
    root = Path(snapshot.snapshot_path)
    combined = "\n".join(
        (root / name).read_text(encoding="utf-8")
        for name in (
            "kernel.jsonl",
            "dispatch.jsonl",
            "reflex-shadow.jsonl",
            "reflex-calibration.jsonl",
        )
    )
    for secret in (
        "SECRET_SOURCE_LABEL",
        "SECRET_SUMMARY",
        "SECRET_DEBUG",
        "SECRET TASK TEXT",
        "SECRET_REMOTE_ID",
        "SECRET_CONTEXT",
        "SECRET_PLAN",
        "SECRET_TOKEN",
        "SECRET_REASON",
        "SECRET_OBSERVER",
        "SECRET_GRANT",
    ):
        assert secret not in combined
    assert snapshot.kernel_rows == 1
    assert snapshot.dispatch_rows == 1
    assert snapshot.reflex_shadow_rows == 1
    assert snapshot.reflex_calibration_rows == 1


def test_snapshot_id_is_deterministic_for_unchanged_observations(tmp_path: Path) -> None:
    state_root = _state(tmp_path)
    _write_sources(state_root)
    exporter = ObservationSnapshotExporter(state_root=state_root)
    a = exporter.export(authority=_authority("ledger.observation.export"))
    b = exporter.export(authority=_authority("ledger.observation.export"))
    assert a.snapshot_id == b.snapshot_id
    assert a.created_at == b.created_at


def test_reflex_authority_material_fails_closed(tmp_path: Path) -> None:
    state_root = _state(tmp_path)
    runs = state_root.parent / "agents" / "runs"
    runs.mkdir(parents=True)
    run = _run()
    shadow = run["shadow_observations"]["phireflex_v0_2"]  # type: ignore[index]
    shadow["action_authority"] = True  # type: ignore[index]
    (runs / f"{run['run_id']}.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden authority"):
        ObservationSnapshotExporter(state_root=state_root).export(
            authority=_authority("ledger.observation.export")
        )


def test_observation_reports_require_separate_read_permission(tmp_path: Path) -> None:
    state_root = _state(tmp_path)
    _write_sources(state_root)
    snapshot = ObservationSnapshotExporter(state_root=state_root).export(
        authority=_authority("ledger.observation.export")
    )
    service = ObservationReportService(state_root=state_root)
    with pytest.raises(PermissionError, match="ledger.observation.read"):
        service.run(
            snapshot_id=snapshot.snapshot_id,
            report_name="kernel_compare_deltas_v1",
            authority=_authority("ledger.observation.export"),
        )


@pytest.mark.parametrize(
    "name",
    [
        "kernel_compare_deltas_v1",
        "agent_dispatch_outcomes_v1",
        "reflex_shadow_agreement_v1",
        "reflex_calibration_summary_v1",
    ],
)
def test_closed_observation_reports_carry_no_authority(tmp_path: Path, name: str) -> None:
    state_root = _state(tmp_path)
    _write_sources(state_root)
    snapshot = ObservationSnapshotExporter(state_root=state_root).export(
        authority=_authority("ledger.observation.export")
    )
    report = ObservationReportService(state_root=state_root).run(
        snapshot_id=snapshot.snapshot_id,
        report_name=name,
        authority=_authority("ledger.observation.read"),
    )
    assert report.report_name == name
    assert report.promotion_status == "not_promoted"
    assert report.action_authority is False
    assert report.execution_authority is False
    assert report.report_sha256 == report.report_id
