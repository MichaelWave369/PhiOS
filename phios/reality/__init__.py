"""Reality Gate verification primitives for PhiOS."""

from .local_http import (
    LocalHttpObservation,
    LocalHttpObservationError,
    LocalHttpStateProvider,
    StdlibLoopbackHttpStateProvider,
    UnavailableLocalHttpStateProvider,
    local_http_url_error,
)
from .local_json import (
    JSON_TYPE_NAMES,
    json_pointer_error,
    json_type_matches,
    json_type_name,
    resolve_json_pointer,
    strict_json_loads,
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
    "JSON_TYPE_NAMES",
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
    "StdlibLoopbackHttpStateProvider",
    "TcpListenerObservation",
    "TcpListenerObservationError",
    "TcpListenerStateProvider",
    "UnavailableLocalHttpStateProvider",
    "json_pointer_error",
    "json_type_matches",
    "json_type_name",
    "local_http_url_error",
    "resolve_json_pointer",
    "strict_json_loads",
]
