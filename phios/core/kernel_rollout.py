"""Kernel rollout compare logging and evaluation helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.core.kernel_runtime import KernelRuntimeConfig, run_kernel_runtime


@dataclass(slots=True)
class KernelCompareRecord:
    id: str
    created_at: str
    context_type: str
    source_label: str
    primary_adapter: str | None
    shadow_adapter: str | None
    primary_verdict: str | None
    shadow_verdict: str | None
    primary_mode: str | None
    shadow_mode: str | None
    primary_coherence_score: float | None
    shadow_coherence_score: float | None
    primary_stability_score: float | None
    shadow_stability_score: float | None
    primary_readiness_score: float | None
    shadow_readiness_score: float | None
    primary_risk_score: float | None
    shadow_risk_score: float | None
    verdict_changed: bool
    recommendation_changed: bool
    score_delta_json: dict[str, float | None]
    null_result_primary: bool
    null_result_shadow: bool
    summary_note: str
    raw_compare_json: dict[str, Any]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "context_type": self.context_type,
            "source_label": self.source_label,
            "primary_adapter": self.primary_adapter,
            "shadow_adapter": self.shadow_adapter,
            "primary_verdict": self.primary_verdict,
            "shadow_verdict": self.shadow_verdict,
            "primary_mode": self.primary_mode,
            "shadow_mode": self.shadow_mode,
            "primary_coherence_score": self.primary_coherence_score,
            "shadow_coherence_score": self.shadow_coherence_score,
            "primary_stability_score": self.primary_stability_score,
            "shadow_stability_score": self.shadow_stability_score,
            "primary_readiness_score": self.primary_readiness_score,
            "shadow_readiness_score": self.shadow_readiness_score,
            "primary_risk_score": self.primary_risk_score,
            "shadow_risk_score": self.shadow_risk_score,
            "verdict_changed": self.verdict_changed,
            "recommendation_changed": self.recommendation_changed,
            "score_delta_json": self.score_delta_json,
            "null_result_primary": self.null_result_primary,
            "null_result_shadow": self.null_result_shadow,
            "summary_note": self.summary_note,
            "raw_compare_json": self.raw_compare_json,
            "fingerprint": self.fingerprint,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root_dir() -> Path:
    home = Path(os.environ.get("PHIOS_CONFIG_HOME", str(Path.home())))
    return home / ".phios" / "kernel_rollout"


def _avg(nums: list[float]) -> float | None:
    if not nums:
        return None
    return round(sum(nums) / len(nums), 6)


class KernelRolloutStore:
    def __init__(self, root: Path | None = None):
        self.root = root or _root_dir()
        self.records_path = self.root / "compare_records.jsonl"
        self.state_path = self.root / "compare_state.json"

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _dedupe_window_seconds(self) -> int:
        raw = os.getenv("PHIOS_KERNEL_COMPARE_DEDUPE_SECONDS", "30")
        try:
            return max(0, int(raw))
        except ValueError:
            return 30

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, ValueError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self._ensure_root()
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def should_skip_duplicate(self, fingerprint: str, created_at: str) -> bool:
        state = self._load_state()
        if state.get("fingerprint") != fingerprint:
            return False
        prev_time_raw = state.get("created_at")
        if not isinstance(prev_time_raw, str):
            return False
        try:
            prev_time = datetime.fromisoformat(prev_time_raw)
            current = datetime.fromisoformat(created_at)
        except ValueError:
            return False
        return (current - prev_time).total_seconds() <= self._dedupe_window_seconds()

    def append(self, record: KernelCompareRecord) -> bool:
        try:
            if self.should_skip_duplicate(record.fingerprint, record.created_at):
                return False
            self._ensure_root()
            with self.records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
            self._save_state({"fingerprint": record.fingerprint, "created_at": record.created_at})
            return True
        except OSError:
            return False

    def read_records(self) -> list[dict[str, Any]]:
        if not self.records_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in self.records_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
        except (OSError, json.JSONDecodeError, ValueError):
            return []
        return rows

    def query_records(
        self,
        *,
        adapter: str | None = None,
        context_type: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.read_records()
        out: list[dict[str, Any]] = []
        since_dt: datetime | None = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError:
                since_dt = None

        for row in rows:
            if adapter and row.get("primary_adapter") != adapter and row.get("shadow_adapter") != adapter:
                continue
            if context_type and row.get("context_type") != context_type:
                continue
            if since_dt and isinstance(row.get("created_at"), str):
                try:
                    row_dt = datetime.fromisoformat(row["created_at"])
                except ValueError:
                    pass
                else:
                    if row_dt < since_dt:
                        continue
            out.append(row)
        return out


def _compute_fingerprint(runtime: dict[str, Any], context_type: str, source_label: str) -> str:
    stable = json.dumps({"runtime": runtime, "context_type": context_type, "source_label": source_label}, sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _build_summary_note(primary: dict[str, Any], shadow: dict[str, Any], deltas: dict[str, Any]) -> str:
    return (
        f"{primary.get('adapter', 'primary')}:{primary.get('verdict', 'unknown')} vs "
        f"{shadow.get('adapter', 'shadow')}:{shadow.get('verdict', 'unknown')} "
        f"(Δcoh={deltas.get('coherence_delta')}, Δrisk={deltas.get('risk_delta')})"
    )


def record_compare_result(
    runtime_result: dict[str, Any],
    *,
    context_type: str,
    source_label: str,
    store: KernelRolloutStore | None = None,
) -> dict[str, Any] | None:
    if not runtime_result.get("enabled"):
        return None
    if not runtime_result.get("compare_mode"):
        return None
    primary = runtime_result.get("primary")
    shadow = runtime_result.get("shadow")
    deltas = runtime_result.get("deltas")
    if not isinstance(primary, dict) or not isinstance(shadow, dict) or not isinstance(deltas, dict):
        return None

    created_at = _now_iso()
    fingerprint = _compute_fingerprint(runtime_result, context_type=context_type, source_label=source_label)
    record = KernelCompareRecord(
        id=fingerprint[:16],
        created_at=created_at,
        context_type=context_type,
        source_label=source_label,
        primary_adapter=primary.get("adapter"),
        shadow_adapter=shadow.get("adapter"),
        primary_verdict=primary.get("verdict"),
        shadow_verdict=shadow.get("verdict"),
        primary_mode=primary.get("mode"),
        shadow_mode=shadow.get("mode"),
        primary_coherence_score=primary.get("coherence_score"),
        shadow_coherence_score=shadow.get("coherence_score"),
        primary_stability_score=primary.get("stability_score"),
        shadow_stability_score=shadow.get("stability_score"),
        primary_readiness_score=primary.get("readiness_score"),
        shadow_readiness_score=shadow.get("readiness_score"),
        primary_risk_score=primary.get("risk_score"),
        shadow_risk_score=shadow.get("risk_score"),
        verdict_changed=bool(deltas.get("verdict_changed")),
        recommendation_changed=bool(deltas.get("recommendation_changed")),
        score_delta_json={
            "coherence_delta": deltas.get("coherence_delta"),
            "stability_delta": deltas.get("stability_delta"),
            "readiness_delta": deltas.get("readiness_delta"),
            "risk_delta": deltas.get("risk_delta"),
        },
        null_result_primary=bool(primary.get("null_result", False)),
        null_result_shadow=bool(shadow.get("null_result", False)),
        summary_note=_build_summary_note(primary, shadow, deltas),
        raw_compare_json={
            "primary": primary,
            "shadow": shadow,
            "deltas": deltas,
        },
        fingerprint=fingerprint,
    )
    target = store or KernelRolloutStore()
    if not target.append(record):
        return None
    return record.to_dict()


def summarize_compare_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    coherence_deltas: list[float] = []
    stability_deltas: list[float] = []
    readiness_deltas: list[float] = []
    risk_deltas: list[float] = []
    verdict_changes = 0
    recommendation_changes = 0
    null_disagreement = 0

    for row in records:
        if row.get("verdict_changed"):
            verdict_changes += 1
        if row.get("recommendation_changed"):
            recommendation_changes += 1
        if bool(row.get("null_result_primary")) != bool(row.get("null_result_shadow")):
            null_disagreement += 1

        deltas = row.get("score_delta_json")
        if not isinstance(deltas, dict):
            continue
        for key, bucket in (
            ("coherence_delta", coherence_deltas),
            ("stability_delta", stability_deltas),
            ("readiness_delta", readiness_deltas),
            ("risk_delta", risk_deltas),
        ):
            val = deltas.get(key)
            if isinstance(val, (int, float)):
                bucket.append(abs(float(val)))

    top = sorted(
        records,
        key=lambda r: abs(float(((r.get("score_delta_json") or {}).get("coherence_delta") or 0.0))),
        reverse=True,
    )[:3]

    return {
        "total_cases": len(records),
        "verdict_changes": verdict_changes,
        "recommendation_changes": recommendation_changes,
        "null_result_disagreement": null_disagreement,
        "avg_score_deltas": {
            "coherence": _avg(coherence_deltas),
            "stability": _avg(stability_deltas),
            "readiness": _avg(readiness_deltas),
            "risk": _avg(risk_deltas),
        },
        "largest_delta_cases": [
            {
                "id": row.get("id"),
                "source_label": row.get("source_label"),
                "coherence_delta": (row.get("score_delta_json") or {}).get("coherence_delta"),
            }
            for row in top
        ],
    }


def recent_rollout_status(store: KernelRolloutStore | None = None, limit: int = 20) -> dict[str, Any]:
    target = store or KernelRolloutStore()
    records = target.read_records()[-limit:]
    summary = summarize_compare_records(records)
    return {
        "recent_samples": len(records),
        **summary,
    }


def export_compare_report(path: str, records: list[dict[str, Any]]) -> Path:
    target = Path(path).expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "exported_at": _now_iso(),
        "summary": summarize_compare_records(records),
        "records": records,
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_eval_cases(path: str | None = None) -> list[dict[str, str]]:
    if path:
        source = Path(path)
    else:
        source = Path(__file__).resolve().parents[1] / "fixtures" / "kernel_eval_cases.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Kernel eval cases must be a JSON array")
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", "case"))
        prompt = str(item.get("prompt", ""))
        out.append({"id": case_id, "prompt": prompt, "context_type": str(item.get("context_type", "eval_case"))})
    return out


def run_kernel_evaluation(
    *,
    adapter: Any,
    cases: list[dict[str, str]],
    config: KernelRuntimeConfig,
    store: KernelRolloutStore | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        runtime = run_kernel_runtime(
            adapter,
            prompt=case.get("prompt") or None,
            config=config,
            context_type=case.get("context_type", "eval_case"),
            source_label=case.get("id", "case"),
            rollout_store=store,
        )
        record = {
            "id": case.get("id"),
            "context_type": case.get("context_type"),
            "runtime": runtime,
        }
        rows.append(record)

    compare_records = [
        row["runtime"].get("compare_record")
        for row in rows
        if isinstance(row.get("runtime"), dict) and isinstance(row["runtime"].get("compare_record"), dict)
    ]
    return {
        "total_cases": len(cases),
        "results": rows,
        "summary": summarize_compare_records(compare_records),
    }
