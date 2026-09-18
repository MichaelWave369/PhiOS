"""Reality Gate verification primitives for PhiOS."""

from .local_network import (
    InterfaceObservation,
    InterfaceObservationError,
    InterfaceStateProvider,
    PsutilInterfaceStateProvider,
)
from .models import (
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    RealityVerificationResult,
)
from .service import RealityVerificationService

__all__ = [
    "InterfaceObservation",
    "InterfaceObservationError",
    "InterfaceStateProvider",
    "PsutilInterfaceStateProvider",
    "RealityClaim",
    "RealityClaimKind",
    "RealityVerdict",
    "RealityVerificationResult",
    "RealityVerificationService",
]
