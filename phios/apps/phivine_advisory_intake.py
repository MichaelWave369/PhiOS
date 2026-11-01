"""Review-only PhiVine -> PhiOS local binary advisory consumer.

This consumes UNTRUSTED JSON produced by PhiVine Rung 7. It is deliberately
separate from public GitHub source repository intake, build, install, runtime
selection, desktop registration, effect leases, and execution services.

Even a correctly checksummed handoff never grants a PhiOS capability.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any

PHIVINE_SCHEMA = "phivine.phios_advisory.v0.1"
REVIEW_SCHEMA = "phios.phivine_advisory_review.v0.1"
MAX_HANDOFF_BYTES = 65536
REQUIRED_GATES = (
    "EXACT_ARTIFACT_HASH_REVALIDATION",
    "RUNNER_BINARY_IDENTITY_AND_VERSION_ATTESTATION",
    "VERIFIED_LINUX_SANDBOX_AND_IDENTITY_BOUNDARY",
    "FILESYSTEM_AND_NETWORK_EFFECT_ENFORCEMENT",
    "EXPLICIT_HUMAN_OPERATOR_AUTHORIZATION",
    "SINGLE_USE_EFFECT_BOUND_LAUNCH_LEASE",
    "PROCESS_LIFECYCLE_AND_TERMINATION_CONTROLS",
    "INDEPENDENT_POST_EFFECT_VERIFICATION_AND_RECEIPTS",
    "PHIOS_NATIVE_WINDOWS_BINARY_INTAKE_REVIEW_REQUIRED",
)
AUTHORITY_FIELDS = (
    "phios_native_binary_intake_exists",
    "phios_api_called",
    "phios_app_registered",
    "trusted_origin_attested",
    "runtime_attested",
    "sandbox_verified",
    "install_authorized",
    "execution_authorized",
    "effect_lease_present",
    "windows_execution_attempted",
)
_TOP_FIELDS = frozenset({
    "schema", "producer", "target", "handoff_type", "status",
    "proposal_id_observed", "artifact", "requested_effects", "observations",
    "authority", "required_before_execution", "limitations", "handoff_id",
})
_OBSERVATION_FIELDS = frozenset({
    "source_status", "stage_status", "runner_status",
    "source_bytes_match_observed", "stage_bytes_match_observed", "runner_elf_observed",
})
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_H_ID = re.compile(r"pha-[0-9a-f]{24}\Z")
_P_ID = re.compile(r"pv-[0-9a-f]{24}\Z")


def _canonical_sha(body: dict[str, Any]) -> str:
    raw = json.dumps(body, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text(value: Any, limit: int) -> bool:
    return (type(value) is str and 0 < len(value) <= limit
            and all(32 <= ord(c) < 127 for c in value))


def _status(value: Any, *, success: str | None, absent: str | None = None) -> bool:
    if not _text(value, 160):
        return False
    return value == success or value == absent or value.startswith("HELD_")


def _valid_handoff(payload: Any) -> bool:
    """Strictly validate the Rung 7 data shape, including immutable false flags.

    The public SHA-based ID is a *checksum*, not a signature. This parser
    validates format and internal consistency, NOT provenance or trust.
    """
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        return False
    if (payload["schema"] != PHIVINE_SCHEMA or payload["producer"] != "phivine"
            or payload["target"] != "phios"
            or payload["handoff_type"] != "local_windows_binary_advisory"):
        return False
    ident = payload["handoff_id"]
    if not isinstance(ident, str) or not _H_ID.fullmatch(ident):
        return False
    try:
        expected = "pha-" + _canonical_sha({k: v for k, v in payload.items()
                                             if k != "handoff_id"})[:24]
        if not hmac.compare_digest(ident, expected):
            return False
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        return False

    authority = payload["authority"]
    if not isinstance(authority, dict) or set(authority) != set(AUTHORITY_FIELDS):
        return False
    if any(authority[k] is not False for k in AUTHORITY_FIELDS):
        return False
    if payload["required_before_execution"] != list(REQUIRED_GATES):
        return False
    limitations = payload["limitations"]
    if (not isinstance(limitations, list) or not 3 <= len(limitations) <= 10
            or any(not _text(note, 300) for note in limitations)):
        return False

    obs = payload["observations"]
    if not isinstance(obs, dict) or set(obs) != _OBSERVATION_FIELDS:
        return False
    if any(type(obs[key]) is not bool for key in (
        "source_bytes_match_observed", "stage_bytes_match_observed",
        "runner_elf_observed"
    )):
        return False

    if payload["status"] == "HELD_INVALID_OR_TAMPERED_PROPOSAL":
        return (payload["proposal_id_observed"] is None
                and payload["artifact"] is None
                and payload["requested_effects"] is None
                and obs["source_status"] == "NOT_CHECKED_INVALID_PLAN"
                and obs["stage_status"] == "NOT_CHECKED_INVALID_PLAN"
                and obs["runner_status"] == "NOT_CHECKED_INVALID_PLAN"
                and not any(obs[k] for k in (
                    "source_bytes_match_observed", "stage_bytes_match_observed",
                    "runner_elf_observed"
                )))

    if payload["status"] != "HELD_PHIOS_BINARY_INTAKE_NOT_IMPLEMENTED":
        return False
    pid = payload["proposal_id_observed"]
    if not isinstance(pid, str) or not _P_ID.fullmatch(pid):
        return False
    artifact = payload["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "name", "sha256_observed", "size_bytes_observed",
        "format_observed", "architecture_observed",
    }:
        return False
    name = artifact["name"]
    if (not _text(name, 255) or name in (".", "..")
            or "/" in name or chr(92) in name or not name.lower().endswith((".exe", ".msi"))):
        return False
    sha = artifact["sha256_observed"]
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        return False
    size = artifact["size_bytes_observed"]
    if type(size) is not int or not 1 <= size <= 512 * 1024 * 1024:
        return False
    if artifact["format_observed"] not in ("pe", "pe_candidate", "msi_cfb_candidate", "unknown"):
        return False
    if artifact["architecture_observed"] not in ("x86", "x86_64", "arm64", None):
        return False

    effects = payload["requested_effects"]
    if not isinstance(effects, dict) or set(effects) != {
        "runner_family_requested", "network", "extra_host_filesystem_access"
    }:
        return False
    if (effects["runner_family_requested"] != "wine"
            or effects["network"] not in ("deny_requested", "operator_review_requested")
            or effects["extra_host_filesystem_access"] != "not_requested"):
        return False

    checks = (
        ("source_status", "source_bytes_match_observed",
         "ARTIFACT_MATCHED_STILL_NOT_RUNNABLE", None),
        ("stage_status", "stage_bytes_match_observed",
         "STAGE_MATCHED_NOT_IMMUTABLE_NOT_RUNNABLE", "NOT_REQUESTED"),
        ("runner_status", "runner_elf_observed",
         "RUNNER_RESOLVED_ELF_OBSERVED_NOT_ATTESTED", "NOT_REQUESTED"),
    )
    for status_field, boolean_field, matching_status, absent in checks:
        val = obs[status_field]
        if not _status(val, success=matching_status, absent=absent):
            return False
        if obs[boolean_field] is not (val == matching_status):
            return False
    return True


def _review(status: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    good = payload is not None and payload["status"] == "HELD_PHIOS_BINARY_INTAKE_NOT_IMPLEMENTED"
    record: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "status": status,
        "input_kind": "untrusted_local_windows_binary_advisory",
        "source_schema": PHIVINE_SCHEMA,
        "handoff_id_observed": payload["handoff_id"] if payload is not None else None,
        "artifact": payload["artifact"] if good else None,
        "requested_effects": payload["requested_effects"] if good else None,
        "observations": payload["observations"] if good else None,
        "unmet_execution_gates": list(REQUIRED_GATES),
        "repo_profile_schema_used": False,
        "repo_compatibility_classification_performed": False,
        "app_registry_read_or_modified": False,
        "phios_install_or_launch_called": False,
        "operator_approval_minted": False,
        "effect_lease_issued": False,
        "execution_authorized": False,
        "windows_binary_executed": False,
        "note": (
            "Read-only untrusted record review; not a native Windows binary intake, "
            "compatibility verdict, permission, install or launch approval."
        ),
    }
    record["review_id"] = "pvr-" + _canonical_sha(record)[:24]
    return record


def review_phivine_advisory(payload: Any) -> dict[str, Any]:
    """Validate and display one PhiVine report without side effects."""
    if not _valid_handoff(payload):
        return _review("HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY")
    if payload["status"] == "HELD_INVALID_OR_TAMPERED_PROPOSAL":
        return _review("HELD_PHIVINE_PROPOSAL_INVALID", payload=payload)
    return _review("HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE", payload=payload)


def read_phivine_advisory_json(path: str | Path) -> Any:
    """Read a bounded local JSON file only; no network or subprocess."""
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError("PhiVine advisory must be a local regular file, not a symlink")
    if source.stat().st_size > MAX_HANDOFF_BYTES:
        raise ValueError("PhiVine advisory exceeds the 64 KiB limit")
    with source.open("rb") as handle:
        content = handle.read(MAX_HANDOFF_BYTES + 1)
    if len(content) > MAX_HANDOFF_BYTES:
        raise ValueError("PhiVine advisory exceeds the 64 KiB limit")
    try:
        return json.loads(content)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("PhiVine advisory is not valid JSON") from exc
