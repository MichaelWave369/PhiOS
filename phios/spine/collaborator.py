from __future__ import annotations

from typing import Any

from .models import PhiPlan


class PhiVesselAdapter:
    """The collaborator seam for Spine v0.1.

    v0.1 is deterministic on purpose: it proves the authority boundary before
    attaching any model-driven planner. Later PhiVessel routing can implement
    the same plan contract without gaining execution authority.
    """

    def plan(self, capability_id: str, payload: dict[str, Any]) -> PhiPlan:
        return PhiPlan(capability_id=capability_id, payload=dict(payload))
