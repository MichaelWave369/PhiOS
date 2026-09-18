"""Reality Gate verification primitives for PhiOS."""

from .local_network import (
    InterfaceObservation,
    InterfaceObservationError,
    InterfaceStateProvider,
    PsutilInterfaceStateProvider,
)
from .local_socket import (
    PsutilTcpListenerStateProvider,
    TcpListenerObservation,
    TcpListenerObservationError,
    TcpListenerStateProvider,
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
    "PsutilTcpListenerStateProvider",
    "RealityClaim",
    "RealityClaimKind",
    "RealityVerdict",
    "RealityVerificationResult",
    "RealityVerificationService",
    "TcpListenerObservation",
    "TcpListenerObservationError",
    "TcpListenerStateProvider",
]
