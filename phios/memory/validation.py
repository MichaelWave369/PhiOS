from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_TEXT_BYTES = 64 * 1024


def strict_canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(strict_canonical_json(value).encode("utf-8")).hexdigest()


def require_nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def require_sha256(value: str, field: str) -> str:
    normalized = require_nonempty(value, field).lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return normalized


def require_utc_timestamp(value: str, field: str) -> str:
    raw = require_nonempty(value, field)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    normalized = parsed.astimezone(UTC).isoformat()
    return normalized


def validate_finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{field} must be finite")
    return out


def validate_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(f"text exceeds {MAX_TEXT_BYTES} UTF-8 bytes")
    return value
