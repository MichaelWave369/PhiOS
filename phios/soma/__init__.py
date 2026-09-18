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
    "ScreenCaptureError",
    "ScreenCaptureProvider",
    "ScreenObservationResult",
    "ScreenRegion",
    "SomaPerceptionService",
]
