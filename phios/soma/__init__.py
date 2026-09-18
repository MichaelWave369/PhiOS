"""SOMA perception primitives for PhiOS."""

from .acquisition import (
    BoundedTextFileAdapter,
    FileAcquisitionError,
    FileSourcePolicy,
)
from .enhancement import (
    EnhancedFrame,
    PillowUnsharpMaskProvider,
    ScreenEnhancementError,
    ScreenEnhancementProvider,
    ScreenEnhancementSpec,
)
from .models import (
    AcuityStatus,
    FileObservationResult,
    NativeEvidence,
    ObservationResult,
    ScreenBurstResult,
    ScreenEnhancementResult,
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
    "EnhancedFrame",
    "FileAcquisitionError",
    "FileObservationResult",
    "FileSourcePolicy",
    "FrameSharpnessScorer",
    "NativeEvidence",
    "ObservationResult",
    "PillowEdgeSharpnessScorer",
    "PillowScreenCaptureProvider",
    "PillowScreenRecoveryProvider",
    "PillowUnsharpMaskProvider",
    "ScreenBurstResult",
    "ScreenCaptureError",
    "ScreenCaptureProvider",
    "ScreenCrop",
    "ScreenEnhancementError",
    "ScreenEnhancementProvider",
    "ScreenEnhancementResult",
    "ScreenEnhancementSpec",
    "ScreenObservationResult",
    "ScreenRecoveryError",
    "ScreenRecoveryFrames",
    "ScreenRecoveryProvider",
    "ScreenRecoveryResult",
    "ScreenRegion",
    "SharpnessScoreError",
    "SomaPerceptionService",
]
