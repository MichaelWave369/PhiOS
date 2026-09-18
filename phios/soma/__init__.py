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
    ScreenBurstResult,
    ScreenObservationResult,
    ScreenRecoveryResult,
)
from .multishot import (
    FrameSharpnessScorer,
    PillowEdgeSharpnessScorer,
    SharpnessScoreError,
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
    "FrameSharpnessScorer",
    "NativeEvidence",
    "ObservationResult",
    "PillowEdgeSharpnessScorer",
    "PillowScreenCaptureProvider",
    "PillowScreenRecoveryProvider",
    "ScreenBurstResult",
    "ScreenCaptureError",
    "ScreenCaptureProvider",
    "ScreenCrop",
    "ScreenObservationResult",
    "ScreenRecoveryError",
    "ScreenRecoveryFrames",
    "ScreenRecoveryProvider",
    "ScreenRecoveryResult",
    "ScreenRegion",
    "SharpnessScoreError",
    "SomaPerceptionService",
]
