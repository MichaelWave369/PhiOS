"""SOMA perception primitives for PhiOS."""

from .acquisition import (
    BoundedTextFileAdapter,
    FileAcquisitionError,
    FileSourcePolicy,
)
from .models import (
    AcuityStatus,
    FileObservationResult,
    NativeEvidence,
    ObservationResult,
    ScreenObservationResult,
    ScreenRecoveryResult,
)
from .recovery import (
    PillowScreenRecoveryProvider,
    ScreenCrop,
    ScreenRecoveryError,
    ScreenRecoveryFrames,
    ScreenRecoveryProvider,
)
from .screen import (
    CapturedFrame,
    PillowScreenCaptureProvider,
    ScreenCaptureError,
    ScreenCaptureProvider,
    ScreenRegion,
)
from .service import SomaPerceptionService

__all__ = [
    "AcuityStatus",
    "BoundedTextFileAdapter",
    "CapturedFrame",
    "FileAcquisitionError",
    "FileObservationResult",
    "FileSourcePolicy",
    "NativeEvidence",
    "ObservationResult",
    "PillowScreenCaptureProvider",
    "PillowScreenRecoveryProvider",
    "ScreenCaptureError",
    "ScreenCaptureProvider",
    "ScreenCrop",
    "ScreenObservationResult",
    "ScreenRecoveryError",
    "ScreenRecoveryFrames",
    "ScreenRecoveryProvider",
    "ScreenRecoveryResult",
    "ScreenRegion",
    "SomaPerceptionService",
]
