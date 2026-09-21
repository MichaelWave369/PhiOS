"""PhiOS Spine: authority-aware execution with Mandala contracts."""

from .api_keys import (
    API_KEY_AUTH_RECEIPT_SCHEMA_VERSION,
    API_KEY_BOUNDARY_SCHEMA_VERSION,
    API_KEY_LEASE_RECEIPT_SCHEMA_VERSION,
    ApiKeyAuthReceipt,
    ApiKeyBoundary,
    ApiKeyContractError,
    ApiKeyLeaseReceipt,
    InboundApiKeySpec,
    OutboundApiKeyLease,
    OutboundApiKeySpec,
)
from .runtime import PhiOSSpine

__all__ = [
    "API_KEY_AUTH_RECEIPT_SCHEMA_VERSION",
    "API_KEY_BOUNDARY_SCHEMA_VERSION",
    "API_KEY_LEASE_RECEIPT_SCHEMA_VERSION",
    "ApiKeyAuthReceipt",
    "ApiKeyBoundary",
    "ApiKeyContractError",
    "ApiKeyLeaseReceipt",
    "InboundApiKeySpec",
    "OutboundApiKeyLease",
    "OutboundApiKeySpec",
    "PhiOSSpine",
]
__version__ = "0.24.0"
