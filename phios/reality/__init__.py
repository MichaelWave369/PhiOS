"""Reality Gate verification primitives for PhiOS."""

from .local_http import (
    LocalHttpObservation,
    LocalHttpObservationError,
    LocalHttpStateProvider,
    UnavailableLocalHttpStateProvider,
    local_http_url_error,
)
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
    "LocalHttpObservation",
    "LocalHttpObservationError",
    "LocalHttpStateProvider",
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
    "UnavailableLocalHttpStateProvider",
    "local_http_url_error",
]
