"""PhiOS Covenant Runtime contracts.

CR-01 is descriptive and evidentiary only. It creates no authority and performs
no execution.
"""

from .identity import (
    IDENTITY_SEAL_SCHEMA_VERSION,
    IdentitySeal,
    IdentitySubjectKind,
)
from .models import (
    BOUNDARY_CONTEXT_SCHEMA_VERSION,
    BOUNDARY_TRANSITION_REQUEST_SCHEMA_VERSION,
    BoundaryContext,
    BoundaryTransitionRequest,
)
from .receipts import (
    BOUNDARY_TRANSITION_RECEIPT_SCHEMA_VERSION,
    BoundaryTransitionReceipt,
    TransitionStatus,
    transition_receipt,
)
from .zones import TrustZone, actor_zones, allowed_transitions, require_actor_zone, require_transition

__all__ = [
    "BOUNDARY_CONTEXT_SCHEMA_VERSION",
    "BOUNDARY_TRANSITION_RECEIPT_SCHEMA_VERSION",
    "BOUNDARY_TRANSITION_REQUEST_SCHEMA_VERSION",
    "IDENTITY_SEAL_SCHEMA_VERSION",
    "BoundaryContext",
    "BoundaryTransitionReceipt",
    "BoundaryTransitionRequest",
    "IdentitySeal",
    "IdentitySubjectKind",
    "TransitionStatus",
    "TrustZone",
    "actor_zones",
    "allowed_transitions",
    "require_actor_zone",
    "require_transition",
    "transition_receipt",
]
