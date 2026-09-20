"""PhiReflex v0.2 dispatch shadow observation.

The shadow receipt is computed only after the operational planner context and
plan already exist. It binds to hashes of those exact objects and must never be
inserted into either object before planning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from phios.reflex.models import ReflexInput, ReflexShadowReceipt
from phios.reflex.service import PhiReflex


class DispatchShadowContractError(ValueError):
    """Raised when dispatch shadow observation would contaminate planning."""


@dataclass(frozen=True, slots=True)
class DispatchShadowReceipt:
    schema: str
    task_sha256: str
    operational_context_sha256: str
    operational_plan_sha256: str
    reflex_receipt: ReflexShadowReceipt
    planner_influenced_by_reflex: bool
    operational_context_contains_reflex: bool
    operational_plan_contains_reflex: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "task_sha256": self.task_sha256,
            "operational_context_sha256": self.operational_context_sha256,
            "operational_plan_sha256": self.operational_plan_sha256,
            "reflex_receipt": self.reflex_receipt.to_dict(),
            "planner_influenced_by_reflex": self.planner_influenced_by_reflex,
            "operational_context_contains_reflex": (
                self.operational_context_contains_reflex
            ),
            "operational_plan_contains_reflex": (
                self.operational_plan_contains_reflex
            ),
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


def observe_dispatch(
    *,
    task: str,
    operational_context: Mapping[str, Any],
    operational_plan: Mapping[str, Any],
    reflex: PhiReflex,
    external_side_effect: bool,
) -> DispatchShadowReceipt:
    """Observe an already-planned dispatch without changing planner inputs."""

    task_text = task.strip()
    if not task_text:
        raise DispatchShadowContractError("task must be non-empty")

    context_obj = dict(operational_context)
    plan_obj = dict(operational_plan)
    context_contains = _contains_reflex_material(context_obj)
    plan_contains = _contains_reflex_material(plan_obj)
    if context_contains:
        raise DispatchShadowContractError(
            "operational dispatch context already contains PhiReflex material"
        )
    if plan_contains:
        raise DispatchShadowContractError(
            "operational dispatch plan already contains PhiReflex material"
        )

    reflex_receipt = reflex.evaluate(
        ReflexInput(
            task_text=task_text,
            tool_intent=True,
            external_side_effect=external_side_effect,
        )
    )

    task_sha256 = _digest({"task": task_text})
    context_sha256 = _digest(context_obj)
    plan_sha256 = _digest(plan_obj)
    payload: dict[str, object] = {
        "schema": "phios.reflex_dispatch_shadow_receipt.v0.2",
        "task_sha256": task_sha256,
        "operational_context_sha256": context_sha256,
        "operational_plan_sha256": plan_sha256,
        "reflex_receipt": reflex_receipt.to_dict(),
        "planner_influenced_by_reflex": False,
        "operational_context_contains_reflex": False,
        "operational_plan_contains_reflex": False,
        "action_authority": False,
        "execution_authority": False,
    }
    return DispatchShadowReceipt(
        schema="phios.reflex_dispatch_shadow_receipt.v0.2",
        task_sha256=task_sha256,
        operational_context_sha256=context_sha256,
        operational_plan_sha256=plan_sha256,
        reflex_receipt=reflex_receipt,
        planner_influenced_by_reflex=False,
        operational_context_contains_reflex=False,
        operational_plan_contains_reflex=False,
        action_authority=False,
        execution_authority=False,
        receipt_sha256=_digest(payload),
    )


def _contains_reflex_material(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if "reflex" in normalized or "jev" in normalized:
                return True
            if _contains_reflex_material(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_reflex_material(item) for item in value)
    return False


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DispatchShadowContractError(
            "dispatch shadow payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
