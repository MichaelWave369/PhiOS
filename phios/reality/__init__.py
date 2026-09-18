"""Reality Gate verification primitives for PhiOS."""

from .models import (
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    RealityVerificationResult,
)
from .service import RealityVerificationService

__all__ = [
    "RealityClaim",
    "RealityClaimKind",
    "RealityVerdict",
    "RealityVerificationResult",
    "RealityVerificationService",
]
