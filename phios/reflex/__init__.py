"""PhiReflex: bounded advisory System-One decisions for PhiOS."""

from .dispatch_shadow import DispatchShadowReceipt, observe_dispatch
from .outcome_calibration import (
    ProviderCalibration,
    ReflexCalibrationReceipt,
    ReflexOutcomeObservation,
    evaluate_dispatch_outcome,
)
from .models import (
    ROLE_LABELS,
    RISK_LABELS,
    ReflexContractError,
    ReflexDecision,
    ReflexInput,
    ReflexShadowReceipt,
)
from .service import PhiReflex

__all__ = [
    "PhiReflex",
    "DispatchShadowReceipt",
    "observe_dispatch",
    "ProviderCalibration",
    "ReflexCalibrationReceipt",
    "ReflexOutcomeObservation",
    "evaluate_dispatch_outcome",
    "ROLE_LABELS",
    "RISK_LABELS",
    "ReflexContractError",
    "ReflexDecision",
    "ReflexInput",
    "ReflexShadowReceipt",
]
