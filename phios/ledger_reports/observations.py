from __future__ import annotations

import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from phios.mandala import AuthorityContext

from .observation_models import ObservationReport, ObservationSnapshot
from .validation import canonical_json_bytes, sha256_bytes, sha256_json, strict_json_loads

OBSERVATION_SCHEMA_VERSION = "phios.ledger_observations.v0.1"
OBSERVATION_REPORT_CATALOG_VERSION = "phios.ledger_observation_reports.v0.1"
MAX_KERNEL_BYTES = 32 * 1024 * 1024
MAX_RUN_FILE_BYTES = 4 * 1024 * 1024
MAX_RUN_FILES = 2000
MAX_JSON_DEPTH = 32
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ADAPTERS = {"legacy", "tiekat_v50"}
_SAFE_DISPATCH_STATUS = {"running", "completed", "cancelled", "failed", "partial", "unknown"}
_SAFE_OUTCOMES = {
    "pending",
    "succeeded",
    "failed",
    "cancelled",
    "cancelled_by_operator",
    "partial",
    "unknown",
}


class ObservationSnapshotExporter:
    """Export allowlisted observational evidence from fixed PhiOS subsystem stores."""

    def __init__(self, *, state_root: Path) -> None:
        self.state_root = state_root.expanduser().resolve()
        self.phios_root = self.state_root.parent
        self.output_root = self.state_root / "derived" / "observations"

    def export(self, *, authority: AuthorityContext) -> ObservationSnapshot:
        if not authority.allows("ledger.observation.export"):
            raise PermissionError("ledger.observation.export permission is required")

        kernel_rows, kernel_source = self._kernel_rows()
        dispatch_rows, shadow_rows, calibration_rows, agent_source = self._agent_rows()

        projected = {
            "kernel.jsonl": _jsonl(kernel_rows),
            "dispatch.jsonl": _jsonl(dispatch_rows),
            "reflex-shadow.jsonl": _jsonl(shadow_rows),
            "reflex-calibration.jsonl": _jsonl(calibration_rows),
        }
        source_digest = sha256_json(
            {
                "kernel": kernel_source,
                "agents": agent_source,
            }
        )
        core = {
            "artifact_kind": OBSERVATION_SCHEMA_VERSION,
            "source_digest": source_digest,
            "files": {
                name: {
                    "sha256": sha256_bytes(data),
                    "rows": len(data.splitlines()),
                }
                for name, data in sorted(projected.items())
            },
            "promotion_status": "not_promoted",
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        snapshot_id = sha256_json(core)
        final_dir = self.output_root / snapshot_id
        created_at = datetime.now(UTC).isoformat()
        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "core": core,
        }
        effective_created_at = self._publish(final_dir, manifest, projected)
        return ObservationSnapshot(
            snapshot_id=snapshot_id,
            snapshot_path=str(final_dir),
            created_at=effective_created_at,
            kernel_rows=len(kernel_rows),
            dispatch_rows=len(dispatch_rows),
            reflex_shadow_rows=len(shadow_rows),
            reflex_calibration_rows=len(calibration_rows),
            source_digest=source_digest,
        )

    def _kernel_rows(self) -> tuple[list[dict[str, Any]], dict[str, object]]:
        path = self.phios_root / "kernel_rollout" / "compare_records.jsonl"
        if path.is_symlink():
            raise ValueError("kernel rollout observations must not be a symlink")
        if not path.exists():
            return [], {"state": "absent"}
        raw = _read_stable_regular(path, MAX_KERNEL_BYTES, "kernel rollout observations")
        complete_end = raw.rfind(b"\n") + 1
        captured = raw[:complete_end]
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(captured.splitlines(), start=1):
            value = strict_json_loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"kernel rollout row {index} must be an object")
            rows.append(_project_kernel(value))
        return rows, {
            "state": "present",
            "sha256": sha256_bytes(captured),
            "captured_bytes": len(captured),
            "partial_tail_bytes": len(raw) - len(captured),
            "rows": len(rows),
        }

    def _agent_rows(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, object],
    ]:
        runs_dir = self.phios_root / "agents" / "runs"
        if runs_dir.is_symlink():
            raise ValueError("agent runs directory must not be a symlink")
        if not runs_dir.exists():
            return [], [], [], {"state": "absent"}

        paths = sorted(runs_dir.glob("run_*.json"))
        paths = [path for path in paths if not path.name.endswith(".events.json")]
        if len(paths) > MAX_RUN_FILES:
            raise ValueError("agent observation file count exceeds configured bound")

        dispatch_rows: list[dict[str, Any]] = []
        shadow_rows: list[dict[str, Any]] = []
        calibration_rows: list[dict[str, Any]] = []
        source_hashes: list[dict[str, object]] = []
        for path in paths:
            if path.is_symlink():
                raise ValueError("agent run observation must not be a symlink")
            raw = _read_stable_regular(path, MAX_RUN_FILE_BYTES, "agent run observation")
            value = strict_json_loads(raw)
            if not isinstance(value, dict):
                raise ValueError("agent run observation must be a JSON object")
            run_id = _bounded_text(value.get("run_id"), "run_id", 128)
            if path.name != f"{run_id}.json":
                raise ValueError("agent run filename does not match run_id")
            dispatch_rows.append(_project_dispatch(value))
            shadow = _project_reflex_shadow(value)
            if shadow is not None:
                shadow_rows.append(shadow)
            calibration_rows.extend(_project_calibrations(value))
            source_hashes.append(
                {
                    "run_id": run_id,
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                }
            )
        return (
            dispatch_rows,
            shadow_rows,
            calibration_rows,
            {
                "state": "present",
                "files": source_hashes,
                "file_count": len(source_hashes),
            },
        )

    def _publish(
        self,
        final_dir: Path,
        manifest: dict[str, Any],
        projected: dict[str, bytes],
    ) -> str:
        self.output_root.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            return _validate_existing(final_dir, manifest)
        temp_dir = Path(tempfile.mkdtemp(prefix=".observation-", dir=str(self.output_root)))
        try:
            for name, data in projected.items():
                _write_fsync(temp_dir / name, data)
            _write_fsync(
                temp_dir / "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
                + b"\n",
            )
            try:
                temp_dir.rename(final_dir)
            except FileExistsError:
                return _validate_existing(final_dir, manifest)
            return str(manifest["created_at"])
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)


class ObservationReportService:
    def __init__(self, *, state_root: Path) -> None:
        self.state_root = state_root.expanduser().resolve()

    def run(
        self,
        *,
        snapshot_id: str,
        report_name: str,
        authority: AuthorityContext,
    ) -> ObservationReport:
        if not authority.allows("ledger.observation.read"):
            raise PermissionError("ledger.observation.read permission is required")
        builder = _REPORTS.get(report_name)
        if builder is None:
            raise ValueError(f"unknown observation report name: {report_name}")
        root, manifest = _load_snapshot(self.state_root, snapshot_id)
        rows = builder(root)
        core = {
            "artifact_kind": "phios.ledger_observation_report.v0.1",
            "catalog_version": OBSERVATION_REPORT_CATALOG_VERSION,
            "report_name": report_name,
            "snapshot_id": snapshot_id,
            "source_digest": manifest["core"]["source_digest"],
            "rows": rows,
            "promotion_status": "not_promoted",
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        report_id = sha256_json(core)
        created_at = _publish_report(self.state_root, report_id, core)
        return ObservationReport(
            report_id=report_id,
            report_name=report_name,
            snapshot_id=snapshot_id,
            created_at=created_at,
            rows=tuple(rows),
            report_sha256=report_id,
        )


def list_observation_reports() -> tuple[tuple[str, str], ...]:
    return (
        ("kernel_compare_deltas_v1", "Summarize kernel primary/shadow comparison changes."),
        ("agent_dispatch_outcomes_v1", "Count persisted dispatch status/outcome observations."),
        ("reflex_shadow_agreement_v1", "Summarize PhiReflex shadow availability and agreement."),
        ("reflex_calibration_summary_v1", "Summarize persisted PhiReflex calibration scores."),
    )


def _project_kernel(row: dict[str, Any]) -> dict[str, Any]:
    primary_adapter = _optional_bounded_text(row.get("primary_adapter"), "primary_adapter", 64)
    shadow_adapter = _optional_bounded_text(row.get("shadow_adapter"), "shadow_adapter", 64)
    for adapter in (primary_adapter, shadow_adapter):
        if adapter is not None and adapter not in _SAFE_ADAPTERS:
            raise ValueError("kernel observation contains unsupported adapter")
    deltas = row.get("score_delta_json")
    if not isinstance(deltas, dict):
        raise ValueError("kernel observation score_delta_json must be an object")
    projected_deltas = {
        key: _optional_finite(deltas.get(key), key)
        for key in (
            "coherence_delta",
            "stability_delta",
            "readiness_delta",
            "risk_delta",
        )
    }
    return {
        "id": _bounded_text(row.get("id"), "id", 128),
        "created_at": _bounded_text(row.get("created_at"), "created_at", 128),
        "context_type": _bounded_text(row.get("context_type"), "context_type", 128),
        "primary_adapter": primary_adapter,
        "shadow_adapter": shadow_adapter,
        "primary_verdict": _optional_bounded_text(row.get("primary_verdict"), "primary_verdict", 128),
        "shadow_verdict": _optional_bounded_text(row.get("shadow_verdict"), "shadow_verdict", 128),
        "primary_mode": _optional_bounded_text(row.get("primary_mode"), "primary_mode", 64),
        "shadow_mode": _optional_bounded_text(row.get("shadow_mode"), "shadow_mode", 64),
        "primary_coherence_score": _optional_finite(row.get("primary_coherence_score"), "primary_coherence_score"),
        "shadow_coherence_score": _optional_finite(row.get("shadow_coherence_score"), "shadow_coherence_score"),
        "primary_stability_score": _optional_finite(row.get("primary_stability_score"), "primary_stability_score"),
        "shadow_stability_score": _optional_finite(row.get("shadow_stability_score"), "shadow_stability_score"),
        "primary_readiness_score": _optional_finite(row.get("primary_readiness_score"), "primary_readiness_score"),
        "shadow_readiness_score": _optional_finite(row.get("shadow_readiness_score"), "shadow_readiness_score"),
        "primary_risk_score": _optional_finite(row.get("primary_risk_score"), "primary_risk_score"),
        "shadow_risk_score": _optional_finite(row.get("shadow_risk_score"), "shadow_risk_score"),
        "verdict_changed": _bool(row.get("verdict_changed"), "verdict_changed"),
        "recommendation_changed": _bool(row.get("recommendation_changed"), "recommendation_changed"),
        "null_result_primary": _bool(row.get("null_result_primary"), "null_result_primary"),
        "null_result_shadow": _bool(row.get("null_result_shadow"), "null_result_shadow"),
        "score_deltas": projected_deltas,
        "fingerprint": _sha(row.get("fingerprint"), "fingerprint"),
    }


def _project_dispatch(run: dict[str, Any]) -> dict[str, Any]:
    status = _bounded_text(run.get("status", "unknown"), "status", 64).lower()
    if status not in _SAFE_DISPATCH_STATUS:
        status = "unknown"
    outcome = _bounded_text(run.get("outcome", "unknown"), "outcome", 64).lower()
    if outcome not in _SAFE_OUTCOMES:
        outcome = "unknown"
    plan = run.get("plan")
    plan_source = None
    planner_available = None
    plan_step_count = 0
    if isinstance(plan, dict):
        plan_source = _optional_bounded_text(plan.get("source"), "plan.source", 64)
        available = plan.get("planner_available")
        if available is not None:
            planner_available = _bool(available, "plan.planner_available")
        steps = plan.get("plan_steps")
        if isinstance(steps, list):
            plan_step_count = len(steps)
    calibrations = run.get("reflex_calibration_receipts")
    calibration_count = len(calibrations) if isinstance(calibrations, list) else 0
    shadows = run.get("shadow_observations")
    shadow_present = isinstance(shadows, dict) and isinstance(shadows.get("phireflex_v0_2"), dict)
    return {
        "run_id": _bounded_text(run.get("run_id"), "run_id", 128),
        "status": status,
        "created_at": _bounded_text(run.get("created_at"), "created_at", 128),
        "updated_at": _bounded_text(run.get("updated_at"), "updated_at", 128),
        "stream_requested": _bool(run.get("stream_requested", False), "stream_requested"),
        "remote_status": _optional_bounded_text(run.get("remote_status"), "remote_status", 128),
        "outcome": outcome,
        "plan_source": plan_source,
        "planner_available": planner_available,
        "plan_step_count": plan_step_count,
        "reflex_shadow_present": shadow_present,
        "reflex_calibration_count": calibration_count,
    }


def _project_reflex_shadow(run: dict[str, Any]) -> dict[str, Any] | None:
    shadows = run.get("shadow_observations")
    if not isinstance(shadows, dict):
        return None
    receipt = shadows.get("phireflex_v0_2")
    if not isinstance(receipt, dict):
        return None
    if receipt.get("schema") != "phios.reflex_dispatch_shadow_receipt.v0.2":
        raise ValueError("unsupported persisted PhiReflex shadow schema")
    if receipt.get("action_authority") is not False or receipt.get("execution_authority") is not False:
        raise ValueError("persisted PhiReflex shadow carries forbidden authority")
    reflex = receipt.get("reflex_receipt")
    if not isinstance(reflex, dict) or reflex.get("schema") != "phios.reflex_shadow_receipt.v0.1":
        raise ValueError("persisted PhiReflex nested receipt is invalid")
    if reflex.get("action_authority") is not False or reflex.get("execution_authority") is not False:
        raise ValueError("persisted PhiReflex nested receipt carries forbidden authority")
    baseline = _project_reflex_decision(reflex.get("baseline"), "baseline")
    shadow_obj = reflex.get("shadow")
    shadow = _project_reflex_decision(shadow_obj, "shadow") if shadow_obj is not None else None
    return {
        "run_id": _bounded_text(run.get("run_id"), "run_id", 128),
        "receipt_sha256": _sha(receipt.get("receipt_sha256"), "receipt_sha256"),
        "shadow_receipt_sha256": _sha(reflex.get("receipt_sha256"), "shadow_receipt_sha256"),
        "shadow_status": _bounded_text(reflex.get("shadow_status"), "shadow_status", 32),
        "shadow_provider": _bounded_text(reflex.get("shadow_provider"), "shadow_provider", 128),
        "role_agreement": _optional_bool(reflex.get("role_agreement"), "role_agreement"),
        "risk_agreement": _optional_bool(reflex.get("risk_agreement"), "risk_agreement"),
        "baseline": baseline,
        "shadow": shadow,
    }


def _project_calibrations(run: dict[str, Any]) -> list[dict[str, Any]]:
    items = run.get("reflex_calibration_receipts")
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("reflex_calibration_receipts must be an array")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("reflex calibration receipt must be an object")
        if item.get("schema") != "phios.reflex_calibration_receipt.v0.3":
            raise ValueError("unsupported PhiReflex calibration schema")
        if item.get("action_authority") is not False or item.get("execution_authority") is not False:
            raise ValueError("PhiReflex calibration carries forbidden authority")
        observation = item.get("observation")
        if not isinstance(observation, dict):
            raise ValueError("PhiReflex calibration observation must be an object")
        out.append(
            {
                "run_id": _bounded_text(item.get("run_id"), "run_id", 128),
                "receipt_sha256": _sha(item.get("receipt_sha256"), "receipt_sha256"),
                "status": _bounded_text(item.get("status"), "status", 64),
                "dispatch_outcome": _bounded_text(observation.get("dispatch_outcome"), "dispatch_outcome", 64),
                "evidence_sha256": _sha(observation.get("evidence_sha256"), "evidence_sha256"),
                "actual_role": _optional_bounded_text(observation.get("actual_role"), "actual_role", 64),
                "actual_risk": _optional_bounded_text(observation.get("actual_risk"), "actual_risk", 64),
                "system2_needed": _optional_bool(observation.get("system2_needed"), "system2_needed"),
                "verification_needed": _optional_bool(observation.get("verification_needed"), "verification_needed"),
                "baseline": _project_calibration_provider(item.get("baseline"), "baseline"),
                "shadow_status": _bounded_text(item.get("shadow_status"), "shadow_status", 32),
                "shadow": (
                    _project_calibration_provider(item.get("shadow"), "shadow")
                    if item.get("shadow") is not None
                    else None
                ),
                "compared_providers": _bool(item.get("compared_providers"), "compared_providers"),
            }
        )
    return out


def _project_reflex_decision(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} PhiReflex decision must be an object")
    if value.get("action_authority") is not False or value.get("execution_authority") is not False:
        raise ValueError(f"{label} PhiReflex decision carries forbidden authority")
    return {
        "provider": _bounded_text(value.get("provider"), f"{label}.provider", 128),
        "model": _bounded_text(value.get("model"), f"{label}.model", 256),
        "role": _bounded_text(value.get("role"), f"{label}.role", 64),
        "risk": _bounded_text(value.get("risk"), f"{label}.risk", 64),
        "confidence": _finite(value.get("confidence"), f"{label}.confidence"),
        "latency_ms": _finite(value.get("latency_ms"), f"{label}.latency_ms"),
        "needs_system2_probability": _finite(
            value.get("needs_system2_probability"),
            f"{label}.needs_system2_probability",
        ),
        "needs_verification_probability": _finite(
            value.get("needs_verification_probability"),
            f"{label}.needs_verification_probability",
        ),
    }


def _project_calibration_provider(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} calibration provider must be an object")
    return {
        "provider": _bounded_text(value.get("provider"), f"{label}.provider", 128),
        "model": _bounded_text(value.get("model"), f"{label}.model", 256),
        "scored_dimensions": _nonnegative_int(value.get("scored_dimensions"), f"{label}.scored_dimensions"),
        "mean_brier": _optional_finite(value.get("mean_brier"), f"{label}.mean_brier"),
        "role_brier": _optional_finite(value.get("role_brier"), f"{label}.role_brier"),
        "risk_brier": _optional_finite(value.get("risk_brier"), f"{label}.risk_brier"),
        "system2_brier": _optional_finite(value.get("system2_brier"), f"{label}.system2_brier"),
        "verification_brier": _optional_finite(
            value.get("verification_brier"),
            f"{label}.verification_brier",
        ),
    }


def _kernel_report(root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(root / "kernel.jsonl")
    grouped: dict[tuple[str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("primary_adapter"), row.get("shadow_adapter"))].append(row)
    out: list[dict[str, Any]] = []
    for (primary, shadow), items in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        deltas = []
        for item in items:
            delta_obj = item.get("score_deltas")
            if isinstance(delta_obj, dict):
                for value in delta_obj.values():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        deltas.append(abs(float(value)))
        out.append(
            {
                "primary_adapter": primary,
                "shadow_adapter": shadow,
                "cases": len(items),
                "verdict_changes": sum(1 for item in items if item.get("verdict_changed") is True),
                "recommendation_changes": sum(
                    1 for item in items if item.get("recommendation_changed") is True
                ),
                "null_result_disagreements": sum(
                    1
                    for item in items
                    if item.get("null_result_primary") != item.get("null_result_shadow")
                ),
                "mean_absolute_score_delta": round(sum(deltas) / len(deltas), 9) if deltas else None,
            }
        )
    return out


def _dispatch_report(root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(root / "dispatch.jsonl")
    counts = Counter(
        (str(row.get("status")), str(row.get("outcome")), str(row.get("remote_status")))
        for row in rows
    )
    return [
        {
            "status": key[0],
            "outcome": key[1],
            "remote_status": key[2],
            "run_count": count,
        }
        for key, count in sorted(counts.items())
    ]


def _reflex_shadow_report(root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(root / "reflex-shadow.jsonl")
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        baseline = row.get("baseline")
        if not isinstance(baseline, dict):
            continue
        key = (str(baseline.get("provider")), str(row.get("shadow_provider")))
        bucket = counts.setdefault(
            key,
            {
                "receipts": 0,
                "shadow_ok": 0,
                "role_agreement": 0,
                "role_scored": 0,
                "risk_agreement": 0,
                "risk_scored": 0,
            },
        )
        bucket["receipts"] += 1
        if row.get("shadow_status") == "ok":
            bucket["shadow_ok"] += 1
        if isinstance(row.get("role_agreement"), bool):
            bucket["role_scored"] += 1
            if row["role_agreement"]:
                bucket["role_agreement"] += 1
        if isinstance(row.get("risk_agreement"), bool):
            bucket["risk_scored"] += 1
            if row["risk_agreement"]:
                bucket["risk_agreement"] += 1
    out: list[dict[str, Any]] = []
    for (baseline_provider, shadow_provider), bucket in sorted(counts.items()):
        out.append(
            {
                "baseline_provider": baseline_provider,
                "shadow_provider": shadow_provider,
                **bucket,
            }
        )
    return out


def _reflex_calibration_report(root: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(root / "reflex-calibration.jsonl")
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        baseline = row.get("baseline")
        shadow = row.get("shadow")
        baseline_provider = (
            str(baseline.get("provider")) if isinstance(baseline, dict) else "unknown"
        )
        shadow_provider = str(shadow.get("provider")) if isinstance(shadow, dict) else "none"
        buckets[(baseline_provider, shadow_provider)].append(row)
    out: list[dict[str, Any]] = []
    for (baseline_provider, shadow_provider), items in sorted(buckets.items()):
        baseline_scores = [
            float(item["baseline"]["mean_brier"])
            for item in items
            if isinstance(item.get("baseline"), dict)
            and isinstance(item["baseline"].get("mean_brier"), (int, float))
            and not isinstance(item["baseline"].get("mean_brier"), bool)
        ]
        shadow_scores = [
            float(item["shadow"]["mean_brier"])
            for item in items
            if isinstance(item.get("shadow"), dict)
            and isinstance(item["shadow"].get("mean_brier"), (int, float))
            and not isinstance(item["shadow"].get("mean_brier"), bool)
        ]
        out.append(
            {
                "baseline_provider": baseline_provider,
                "shadow_provider": shadow_provider,
                "receipts": len(items),
                "scored_receipts": sum(1 for item in items if item.get("status") == "scored"),
                "baseline_mean_brier": (
                    round(sum(baseline_scores) / len(baseline_scores), 9)
                    if baseline_scores
                    else None
                ),
                "shadow_mean_brier": (
                    round(sum(shadow_scores) / len(shadow_scores), 9)
                    if shadow_scores
                    else None
                ),
            }
        )
    return out


_REPORTS: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
    "kernel_compare_deltas_v1": _kernel_report,
    "agent_dispatch_outcomes_v1": _dispatch_report,
    "reflex_shadow_agreement_v1": _reflex_shadow_report,
    "reflex_calibration_summary_v1": _reflex_calibration_report,
}


def _load_snapshot(state_root: Path, snapshot_id: str) -> tuple[Path, dict[str, Any]]:
    if not _SHA_RE.fullmatch(snapshot_id):
        raise ValueError("observation snapshot_id must be a SHA-256 digest")
    root = state_root.expanduser().resolve() / "derived" / "observations" / snapshot_id
    if root.is_symlink():
        raise ValueError("observation snapshot directory must not be a symlink")
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("observation snapshot does not exist") from exc
    manifest = _load_object(root / "manifest.json", "observation manifest")
    if manifest.get("snapshot_id") != snapshot_id:
        raise ValueError("observation snapshot ID mismatch")
    core = manifest.get("core")
    if not isinstance(core, dict) or sha256_json(core) != snapshot_id:
        raise ValueError("observation snapshot core hash mismatch")
    if core.get("artifact_kind") != OBSERVATION_SCHEMA_VERSION:
        raise ValueError("unsupported observation snapshot version")
    if core.get("promotion_status") != "not_promoted":
        raise ValueError("observation snapshot promotion status is invalid")
    for field in ("routing_influence_authority", "action_authority", "execution_authority"):
        if core.get(field) is not False:
            raise ValueError("observation snapshot carries forbidden authority")
    files = core.get("files")
    if not isinstance(files, dict) or set(files) != {
        "kernel.jsonl",
        "dispatch.jsonl",
        "reflex-shadow.jsonl",
        "reflex-calibration.jsonl",
    }:
        raise ValueError("observation snapshot file manifest is invalid")
    for name, item in files.items():
        if not isinstance(item, dict):
            raise ValueError("observation snapshot file entry is invalid")
        raw = _read_stable_regular(root / name, 64 * 1024 * 1024, name)
        if sha256_bytes(raw) != item.get("sha256"):
            raise ValueError("observation snapshot file hash mismatch")
        if len(raw.splitlines()) != item.get("rows"):
            raise ValueError("observation snapshot file row count mismatch")
    return root, manifest


def _validate_existing(root: Path, expected: dict[str, Any]) -> str:
    existing = _load_object(root / "manifest.json", "observation manifest")
    if existing.get("snapshot_id") != expected.get("snapshot_id"):
        raise RuntimeError("existing observation snapshot ID mismatch")
    if existing.get("core") != expected.get("core"):
        raise RuntimeError("existing observation snapshot core mismatch")
    snapshot_id = existing.get("snapshot_id")
    if not isinstance(snapshot_id, str) or sha256_json(existing["core"]) != snapshot_id:
        raise RuntimeError("existing observation snapshot hash mismatch")
    files = existing["core"].get("files")
    if not isinstance(files, dict):
        raise RuntimeError("existing observation snapshot file manifest is invalid")
    for name, item in files.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            raise RuntimeError("existing observation snapshot file entry is invalid")
        raw = _read_stable_regular(root / name, 64 * 1024 * 1024, name)
        if sha256_bytes(raw) != item.get("sha256"):
            raise RuntimeError("existing observation snapshot file hash mismatch")
    created_at = existing.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise RuntimeError("existing observation snapshot created_at is invalid")
    return created_at


def _publish_report(state_root: Path, report_id: str, core: dict[str, Any]) -> str:
    root = state_root.expanduser().resolve() / "derived" / "observation-reports"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{report_id}.json"
    if path.exists():
        existing = _load_object(path, "observation report")
        if (
            existing.get("report_id") != report_id
            or existing.get("report_sha256") != report_id
            or existing.get("core") != core
        ):
            raise RuntimeError("existing observation report mismatch")
        created_at = existing.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeError("existing observation report created_at is invalid")
        return created_at
    created_at = datetime.now(UTC).isoformat()
    payload = {
        "report_id": report_id,
        "report_sha256": report_id,
        "created_at": created_at,
        "core": core,
    }
    _write_fsync(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n")
    return created_at


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _read_stable_regular(path, 64 * 1024 * 1024, path.name)
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} row must be an object")
        rows.append(value)
    return rows


def _load_object(path: Path, label: str) -> dict[str, Any]:
    raw = _read_stable_regular(path, 8 * 1024 * 1024, label)
    value = strict_json_loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _read_stable_regular(path: Path, max_bytes: int, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if before.st_size > max_bytes:
            raise ValueError(f"{label} exceeds size limit")
        raw = os.read(fd, before.st_size)
        after = os.fstat(fd)
        if len(raw) != before.st_size or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise RuntimeError(f"{label} changed during capture")
        if after.st_size != before.st_size:
            raise RuntimeError(f"{label} changed size during capture")
        return raw
    finally:
        os.close(fd)


def _write_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _bounded_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be a non-empty bounded string")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise ValueError(f"{field} contains control characters")
    return value


def _optional_bounded_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field, maximum)


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    return _bool(value, field)


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _optional_finite(value: object, field: str) -> float | None:
    if value is None:
        return None
    return _finite(value, field)


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 digest")
    return value
