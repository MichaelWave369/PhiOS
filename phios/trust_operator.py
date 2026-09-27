"""Trusted local PhiVessel execution configuration operator for v0.37.

The operator owns local trust configuration. Browser/model callers never call
this module directly. Authority mutations are reconstructed from an append-only
local event state and materialized into the existing sealed execution manifest.

Static trust changes require a host restart. AuthorityEpoch-only changes remain
live-visible to the already-mounted ManifestAuthorityEpochProvider.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Mapping

from phios.authority_epoch import AuthorityEpoch, AuthorityEpochContractError
from phios.mandala import (
    AuthoritativeAuthorityEvent,
    AuthorityEventKind,
    AuthorityProjectionError,
)
from phios.phivessel_local_execution import (
    PhiVesselLocalExecutionError,
    PhiVesselLocalExecutionManifest,
)

TRUST_AUTHORITY_STATE_SCHEMA_VERSION = "phios.trust_authority_state.v0.37"
TRUST_MUTATION_JOURNAL_SCHEMA_VERSION = "phios.trust_mutation_journal.v0.37"
TRUST_MUTATION_RECEIPT_SCHEMA_VERSION = "phios.trust_mutation_receipt.v0.37"
DEFAULT_AUTHORITY_STATE_FILENAME = "phivessel-authority-events.json"
DEFAULT_TRUST_JOURNAL_FILENAME = "phivessel-trust.pending.json"
DEFAULT_TRUST_LOCK_FILENAME = "phivessel-trust.lock"
DEFAULT_TRUST_RECEIPT_FILENAME = "trust-operator-receipts.jsonl"


class PhiVesselTrustOperatorError(ValueError):
    """Raised when trusted local configuration cannot be safely mutated."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PhiVesselTrustOperatorError(
            "trust-operator payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_time(value: datetime | str | None = None) -> str:
    if value is None:
        parsed = datetime.now(UTC)
    elif isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PhiVesselTrustOperatorError(
                "timestamp must be ISO-8601"
            ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PhiVesselTrustOperatorError(
            "timestamp must be timezone-aware"
        )
    return parsed.astimezone(UTC).isoformat()


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise PhiVesselTrustOperatorError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise PhiVesselTrustOperatorError(f"{field} is invalid")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise PhiVesselTrustOperatorError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_string_tuple(
    value: object,
    field: str,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PhiVesselTrustOperatorError(f"{field} must be an array")
    result = tuple(
        _require_text(item, f"{field} item", maximum=256)
        for item in value
    )
    if tuple(sorted(set(result))) != result:
        raise PhiVesselTrustOperatorError(
            f"{field} must be sorted and unique"
        )
    return result


def _parse_event(value: object) -> AuthoritativeAuthorityEvent:
    if not isinstance(value, Mapping):
        raise PhiVesselTrustOperatorError(
            "authority event must be an object"
        )
    data = dict(value)
    expected = {
        "event_id",
        "sequence",
        "kind",
        "permission",
        "authority_source",
        "effective_at",
        "expires_at",
    }
    if set(data) != expected:
        raise PhiVesselTrustOperatorError(
            "authority event fields do not match contract"
        )
    sequence = data["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise PhiVesselTrustOperatorError(
            "authority event sequence must be an integer"
        )
    try:
        kind = AuthorityEventKind(
            _require_text(data["kind"], "authority event kind", maximum=16)
        )
        return AuthoritativeAuthorityEvent(
            event_id=_require_text(
                data["event_id"],
                "authority event id",
                maximum=256,
            ),
            sequence=sequence,
            kind=kind,
            permission=_require_text(
                data["permission"],
                "authority event permission",
                maximum=256,
            ),
            authority_source=_require_text(
                data["authority_source"],
                "authority source",
                maximum=256,
            ),
            effective_at=_canonical_time(
                _require_text(
                    data["effective_at"],
                    "authority event effective_at",
                    maximum=64,
                )
            ),
            expires_at=(
                None
                if data["expires_at"] is None
                else _canonical_time(
                    _require_text(
                        data["expires_at"],
                        "authority event expires_at",
                        maximum=64,
                    )
                )
            ),
        )
    except (ValueError, AuthorityProjectionError) as exc:
        raise PhiVesselTrustOperatorError(
            "authority event is invalid"
        ) from exc


@dataclass(frozen=True, slots=True)
class PhiVesselAuthorityState:
    principal_id: str
    policy_sha256: str
    ceiling: tuple[str, ...]
    bootstrap_manifest_sha256: str
    bootstrap_authority_epoch_sha256: str
    events: tuple[AuthoritativeAuthorityEvent, ...]
    schema_version: str = TRUST_AUTHORITY_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRUST_AUTHORITY_STATE_SCHEMA_VERSION:
            raise PhiVesselTrustOperatorError(
                "unsupported trust authority-state schema"
            )
        _require_text(self.principal_id, "principal_id", maximum=256)
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_sha256(
            self.bootstrap_manifest_sha256,
            "bootstrap_manifest_sha256",
        )
        _require_sha256(
            self.bootstrap_authority_epoch_sha256,
            "bootstrap_authority_epoch_sha256",
        )
        if tuple(sorted(set(self.ceiling))) != self.ceiling:
            raise PhiVesselTrustOperatorError(
                "authority ceiling must be sorted and unique"
            )
        sequences = tuple(event.sequence for event in self.events)
        if sequences != tuple(range(len(self.events))):
            raise PhiVesselTrustOperatorError(
                "authority event sequence must be contiguous from zero"
            )
        ids = tuple(event.event_id for event in self.events)
        if len(set(ids)) != len(ids):
            raise PhiVesselTrustOperatorError(
                "authority event IDs must be unique"
            )
        for event in self.events:
            if event.permission not in set(self.ceiling):
                raise PhiVesselTrustOperatorError(
                    "authority event exceeds the frozen ceiling"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "principal_id": self.principal_id,
            "policy_sha256": self.policy_sha256,
            "ceiling": list(self.ceiling),
            "bootstrap_manifest_sha256": self.bootstrap_manifest_sha256,
            "bootstrap_authority_epoch_sha256": (
                self.bootstrap_authority_epoch_sha256
            ),
            "events": [event.to_dict() for event in self.events],
        }

    @property
    def authority_state_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["authority_state_sha256"] = self.authority_state_sha256
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "PhiVesselAuthorityState":
        if not isinstance(value, Mapping):
            raise PhiVesselTrustOperatorError(
                "authority state must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "principal_id",
            "policy_sha256",
            "ceiling",
            "bootstrap_manifest_sha256",
            "bootstrap_authority_epoch_sha256",
            "events",
            "authority_state_sha256",
        }
        if set(data) != expected:
            raise PhiVesselTrustOperatorError(
                "authority-state fields do not match contract"
            )
        raw_events = data["events"]
        if not isinstance(raw_events, list):
            raise PhiVesselTrustOperatorError(
                "authority-state events must be an array"
            )
        item = cls(
            principal_id=_require_text(
                data["principal_id"],
                "principal_id",
                maximum=256,
            ),
            policy_sha256=_require_sha256(
                data["policy_sha256"],
                "policy_sha256",
            ),
            ceiling=_require_string_tuple(data["ceiling"], "ceiling"),
            bootstrap_manifest_sha256=_require_sha256(
                data["bootstrap_manifest_sha256"],
                "bootstrap_manifest_sha256",
            ),
            bootstrap_authority_epoch_sha256=_require_sha256(
                data["bootstrap_authority_epoch_sha256"],
                "bootstrap_authority_epoch_sha256",
            ),
            events=tuple(_parse_event(event) for event in raw_events),
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=128,
            ),
        )
        claimed = _require_sha256(
            data["authority_state_sha256"],
            "authority_state_sha256",
        )
        if claimed != item.authority_state_sha256:
            raise PhiVesselTrustOperatorError(
                "authority-state SHA-256 mismatch"
            )
        return item

    @classmethod
    def read(cls, path: Path) -> "PhiVesselAuthorityState":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhiVesselTrustOperatorError(
                "authority state could not be read safely"
            ) from exc
        return cls.from_dict(value)

    def epoch(self, *, observed_at: str) -> AuthorityEpoch:
        try:
            return AuthorityEpoch.build(
                principal_id=self.principal_id,
                policy_sha256=self.policy_sha256,
                ceiling=self.ceiling,
                events=self.events,
                observed_at=_canonical_time(observed_at),
            )
        except AuthorityEpochContractError as exc:
            raise PhiVesselTrustOperatorError(
                "authority state cannot reconstruct AuthorityEpoch"
            ) from exc


@dataclass(frozen=True, slots=True)
class TrustMutationReceipt:
    receipt_id: str
    operation: str
    actor_id: str
    previous_manifest_sha256: str
    next_manifest_sha256: str
    previous_authority_epoch_sha256: str
    next_authority_epoch_sha256: str
    authority_state_sha256: str | None
    authority_event_id: str | None
    restart_required: bool
    applied_at: str
    effect_performed: bool = True
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = TRUST_MUTATION_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "operation": self.operation,
            "actor_id": self.actor_id,
            "previous_manifest_sha256": self.previous_manifest_sha256,
            "next_manifest_sha256": self.next_manifest_sha256,
            "previous_authority_epoch_sha256": (
                self.previous_authority_epoch_sha256
            ),
            "next_authority_epoch_sha256": (
                self.next_authority_epoch_sha256
            ),
            "authority_state_sha256": self.authority_state_sha256,
            "authority_event_id": self.authority_event_id,
            "restart_required": self.restart_required,
            "applied_at": self.applied_at,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True, slots=True)
class TrustMutationJournal:
    operation: str
    previous_manifest_sha256: str
    previous_authority_epoch_sha256: str
    next_manifest: PhiVesselLocalExecutionManifest
    next_authority_state: PhiVesselAuthorityState | None
    authority_event_id: str | None
    restart_required: bool
    prepared_at: str
    schema_version: str = TRUST_MUTATION_JOURNAL_SCHEMA_VERSION

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "previous_manifest_sha256": self.previous_manifest_sha256,
            "previous_authority_epoch_sha256": (
                self.previous_authority_epoch_sha256
            ),
            "next_manifest": self.next_manifest.to_dict(),
            "next_authority_state": (
                None
                if self.next_authority_state is None
                else self.next_authority_state.to_dict()
            ),
            "authority_event_id": self.authority_event_id,
            "restart_required": self.restart_required,
            "prepared_at": self.prepared_at,
        }

    @property
    def journal_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["journal_sha256"] = self.journal_sha256
        return payload

    @classmethod
    def from_dict(cls, value: object) -> "TrustMutationJournal":
        if not isinstance(value, Mapping):
            raise PhiVesselTrustOperatorError(
                "trust mutation journal must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "operation",
            "previous_manifest_sha256",
            "previous_authority_epoch_sha256",
            "next_manifest",
            "next_authority_state",
            "authority_event_id",
            "restart_required",
            "prepared_at",
            "journal_sha256",
        }
        if set(data) != expected:
            raise PhiVesselTrustOperatorError(
                "trust mutation journal fields do not match contract"
            )
        try:
            manifest = PhiVesselLocalExecutionManifest.from_dict(
                data["next_manifest"]
            )
        except PhiVesselLocalExecutionError as exc:
            raise PhiVesselTrustOperatorError(
                "journal contains invalid execution manifest"
            ) from exc
        raw_state = data["next_authority_state"]
        state = (
            None
            if raw_state is None
            else PhiVesselAuthorityState.from_dict(raw_state)
        )
        event_id = data["authority_event_id"]
        if event_id is not None:
            event_id = _require_text(
                event_id,
                "authority_event_id",
                maximum=256,
            )
        restart = data["restart_required"]
        if not isinstance(restart, bool):
            raise PhiVesselTrustOperatorError(
                "restart_required must be Boolean"
            )
        item = cls(
            operation=_require_text(
                data["operation"],
                "operation",
                maximum=128,
            ),
            previous_manifest_sha256=_require_sha256(
                data["previous_manifest_sha256"],
                "previous_manifest_sha256",
            ),
            previous_authority_epoch_sha256=_require_sha256(
                data["previous_authority_epoch_sha256"],
                "previous_authority_epoch_sha256",
            ),
            next_manifest=manifest,
            next_authority_state=state,
            authority_event_id=event_id,
            restart_required=restart,
            prepared_at=_canonical_time(
                _require_text(
                    data["prepared_at"],
                    "prepared_at",
                    maximum=64,
                )
            ),
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=128,
            ),
        )
        claimed = _require_sha256(
            data["journal_sha256"],
            "journal_sha256",
        )
        if claimed != item.journal_sha256:
            raise PhiVesselTrustOperatorError(
                "trust mutation journal SHA-256 mismatch"
            )
        return item

    @classmethod
    def read(cls, path: Path) -> "TrustMutationJournal":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhiVesselTrustOperatorError(
                "trust mutation journal could not be read safely"
            ) from exc
        return cls.from_dict(value)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise PhiVesselTrustOperatorError(
                    "another trust-operator mutation is active"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except OSError as exc:
                raise PhiVesselTrustOperatorError(
                    "another trust-operator mutation is active"
                ) from exc
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.tmp"
    )
    encoded = (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _append_jsonl_once(
    path: Path,
    receipt: TrustMutationReceipt,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise PhiVesselTrustOperatorError(
                "trust receipt ledger could not be read safely"
            ) from exc
        for line in existing:
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PhiVesselTrustOperatorError(
                    "trust receipt ledger contains invalid JSON"
                ) from exc
            if (
                isinstance(row, Mapping)
                and row.get("receipt_id") == receipt.receipt_id
            ):
                return
    line = json.dumps(
        receipt.to_dict(),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class PhiVesselTrustOperator:
    """Local human operator surface for the sealed execution manifest."""

    def __init__(
        self,
        *,
        manifest_path: Path,
        authority_state_path: Path,
        journal_path: Path,
        receipt_path: Path,
        lock_path: Path,
        actor_id: str = "operator:local",
    ) -> None:
        self.manifest_path = manifest_path.expanduser()
        self.authority_state_path = authority_state_path.expanduser()
        self.journal_path = journal_path.expanduser()
        self.receipt_path = receipt_path.expanduser()
        self.lock_path = lock_path.expanduser()
        self.actor_id = _require_text(actor_id, "actor_id", maximum=256)

    @classmethod
    def for_manifest(
        cls,
        *,
        manifest_path: Path,
        state_root: Path,
        actor_id: str = "operator:local",
    ) -> "PhiVesselTrustOperator":
        config_root = manifest_path.expanduser().parent
        ledger_root = state_root.expanduser() / "ledger"
        return cls(
            manifest_path=manifest_path,
            authority_state_path=(
                config_root / DEFAULT_AUTHORITY_STATE_FILENAME
            ),
            journal_path=config_root / DEFAULT_TRUST_JOURNAL_FILENAME,
            receipt_path=ledger_root / DEFAULT_TRUST_RECEIPT_FILENAME,
            lock_path=config_root / DEFAULT_TRUST_LOCK_FILENAME,
            actor_id=actor_id,
        )

    def status(self) -> dict[str, object]:
        pending = self.journal_path.exists()
        try:
            manifest = self._read_manifest()
        except FileNotFoundError:
            return {
                "manifest_path": str(self.manifest_path),
                "manifest_present": False,
                "manifest_valid": False,
                "pending_recovery": pending,
                "authority_state_present": self.authority_state_path.exists(),
                "execution_enabled": False,
                "desktop_executor_enabled": False,
                "restart_required_from_status": False,
            }

        state: PhiVesselAuthorityState | None = None
        state_error: str | None = None
        if self.authority_state_path.exists():
            try:
                state = PhiVesselAuthorityState.read(
                    self.authority_state_path
                )
                self._validate_state_against_manifest(state, manifest)
            except PhiVesselTrustOperatorError as exc:
                state_error = str(exc)

        epoch = manifest.authority_epoch
        return {
            "manifest_path": str(self.manifest_path),
            "manifest_present": True,
            "manifest_valid": True,
            "manifest_sha256": manifest.manifest_sha256,
            "static_config_sha256": manifest.static_config_sha256,
            "execution_enabled": manifest.enabled,
            "desktop_executor_enabled": (
                manifest.desktop_executor_enabled
            ),
            "mapping_count": len(manifest.mappings),
            "lease_policy_count": len(manifest.lease_policies),
            "mappings": [
                {
                    "mapping_id": item.mapping_id,
                    "intent_code": item.intent_code,
                    "capability_id": item.capability_id,
                    "capability_version": item.capability_version,
                    "permissions_required": list(
                        item.permissions_required
                    ),
                    "effects_declared": list(item.effects_declared),
                    "mapping_sha256": item.mapping_sha256,
                }
                for item in manifest.mappings
            ],
            "lease_policies": [
                {
                    "policy_id": item.policy_id,
                    "principal_id": item.principal_id,
                    "capability_id": item.capability_id,
                    "capability_version": item.capability_version,
                    "permissions_authorized": list(
                        item.permissions_authorized
                    ),
                    "effects_declared": list(item.effects_declared),
                    "max_lease_seconds": item.max_lease_seconds,
                    "policy_sha256": item.policy_sha256,
                }
                for item in manifest.lease_policies
            ],
            "authority_epoch": {
                "authority_epoch_sha256": epoch.authority_epoch_sha256,
                "principal_id": epoch.principal_id,
                "observed_at": epoch.observed_at,
                "policy_sha256": epoch.policy_sha256,
                "ceiling": list(epoch.ceiling),
                "grants": list(epoch.grants),
                "next_known_transition_at": (
                    epoch.next_known_transition_at
                ),
            },
            "authority_state_present": state is not None,
            "authority_state_sha256": (
                None if state is None else state.authority_state_sha256
            ),
            "authority_state_error": state_error,
            "pending_recovery": pending,
            "restart_required_from_status": False,
        }

    def validate(self) -> dict[str, object]:
        manifest = self._read_manifest()
        state_valid = False
        state_sha: str | None = None
        if self.authority_state_path.exists():
            state = PhiVesselAuthorityState.read(
                self.authority_state_path
            )
            self._validate_state_against_manifest(state, manifest)
            state_valid = True
            state_sha = state.authority_state_sha256
        return {
            "valid": True,
            "manifest_sha256": manifest.manifest_sha256,
            "static_config_sha256": manifest.static_config_sha256,
            "authority_epoch_sha256": (
                manifest.authority_epoch.authority_epoch_sha256
            ),
            "authority_state_present": (
                self.authority_state_path.exists()
            ),
            "authority_state_valid": state_valid,
            "authority_state_sha256": state_sha,
            "pending_recovery": self.journal_path.exists(),
        }

    def bootstrap_authority(
        self,
        *,
        expected_manifest_sha256: str,
        observed_at: str | None = None,
    ) -> TrustMutationReceipt:
        expected = _require_sha256(
            expected_manifest_sha256,
            "expected_manifest_sha256",
        )
        with _exclusive_lock(self.lock_path):
            self._require_no_pending_journal()
            if self.authority_state_path.exists():
                raise PhiVesselTrustOperatorError(
                    "authority event state already exists"
                )
            manifest = self._read_manifest()
            self._require_manifest_identity(manifest, expected)
            old_epoch = manifest.authority_epoch
            if old_epoch.next_known_transition_at is not None:
                raise PhiVesselTrustOperatorError(
                    "cannot bootstrap derived AuthorityEpoch with a known "
                    "future transition; import authoritative event history"
                )
            source = (
                "phios-trust:validated-manifest-bootstrap:"
                + old_epoch.authority_epoch_sha256[:24]
            )
            events = tuple(
                AuthoritativeAuthorityEvent(
                    event_id=(
                        "bootstrap:"
                        + _canonical_sha256(
                            {
                                "epoch": old_epoch.authority_epoch_sha256,
                                "permission": permission,
                            }
                        )[:24]
                    ),
                    sequence=index,
                    kind=AuthorityEventKind.GRANT,
                    permission=permission,
                    authority_source=source,
                    effective_at=old_epoch.observed_at,
                )
                for index, permission in enumerate(old_epoch.grants)
            )
            state = PhiVesselAuthorityState(
                principal_id=old_epoch.principal_id,
                policy_sha256=old_epoch.policy_sha256,
                ceiling=old_epoch.ceiling,
                bootstrap_manifest_sha256=manifest.manifest_sha256,
                bootstrap_authority_epoch_sha256=(
                    old_epoch.authority_epoch_sha256
                ),
                events=events,
            )
            next_epoch = state.epoch(
                observed_at=_canonical_time(observed_at)
            )
            next_manifest = self._manifest_with_epoch(
                manifest,
                next_epoch,
            )
            return self._commit(
                operation="AUTHORITY_BOOTSTRAP",
                previous_manifest=manifest,
                next_manifest=next_manifest,
                next_authority_state=state,
                authority_event_id=None,
                restart_required=False,
            )

    def grant(
        self,
        *,
        permission: str,
        expected_manifest_sha256: str,
        expires_at: str | None = None,
        observed_at: str | None = None,
    ) -> TrustMutationReceipt:
        return self._authority_mutation(
            permission=permission,
            kind=AuthorityEventKind.GRANT,
            expected_manifest_sha256=expected_manifest_sha256,
            expires_at=expires_at,
            observed_at=observed_at,
        )

    def revoke(
        self,
        *,
        permission: str,
        expected_manifest_sha256: str,
        observed_at: str | None = None,
    ) -> TrustMutationReceipt:
        return self._authority_mutation(
            permission=permission,
            kind=AuthorityEventKind.REVOKE,
            expected_manifest_sha256=expected_manifest_sha256,
            expires_at=None,
            observed_at=observed_at,
        )

    def refresh_epoch(
        self,
        *,
        expected_manifest_sha256: str,
        observed_at: str | None = None,
    ) -> TrustMutationReceipt:
        expected = _require_sha256(
            expected_manifest_sha256,
            "expected_manifest_sha256",
        )
        with _exclusive_lock(self.lock_path):
            self._require_no_pending_journal()
            manifest = self._read_manifest()
            self._require_manifest_identity(manifest, expected)
            state = self._read_required_authority_state()
            self._validate_state_against_manifest(state, manifest)
            next_epoch = state.epoch(
                observed_at=_canonical_time(observed_at)
            )
            next_manifest = self._manifest_with_epoch(
                manifest,
                next_epoch,
            )
            return self._commit(
                operation="AUTHORITY_EPOCH_REFRESH",
                previous_manifest=manifest,
                next_manifest=next_manifest,
                next_authority_state=state,
                authority_event_id=None,
                restart_required=False,
            )

    def set_execution_enabled(
        self,
        *,
        enabled: bool,
        expected_manifest_sha256: str,
    ) -> TrustMutationReceipt:
        expected = _require_sha256(
            expected_manifest_sha256,
            "expected_manifest_sha256",
        )
        with _exclusive_lock(self.lock_path):
            self._require_no_pending_journal()
            manifest = self._read_manifest()
            self._require_manifest_identity(manifest, expected)
            if (
                manifest.enabled is enabled
                and manifest.desktop_executor_enabled is enabled
            ):
                raise PhiVesselTrustOperatorError(
                    "execution state already matches requested value"
                )
            next_manifest = PhiVesselLocalExecutionManifest.build(
                enabled=enabled,
                desktop_executor_enabled=enabled,
                mappings=manifest.mappings,
                lease_policies=manifest.lease_policies,
                authority_epoch=manifest.authority_epoch,
            )
            state = (
                None
                if not self.authority_state_path.exists()
                else PhiVesselAuthorityState.read(
                    self.authority_state_path
                )
            )
            if state is not None:
                self._validate_state_against_manifest(
                    state,
                    manifest,
                )
            return self._commit(
                operation=(
                    "EXECUTION_ENABLE"
                    if enabled
                    else "EXECUTION_DISABLE"
                ),
                previous_manifest=manifest,
                next_manifest=next_manifest,
                next_authority_state=state,
                authority_event_id=None,
                restart_required=True,
            )

    def recover(self) -> TrustMutationReceipt:
        with _exclusive_lock(self.lock_path):
            try:
                journal = TrustMutationJournal.read(self.journal_path)
            except FileNotFoundError as exc:
                raise PhiVesselTrustOperatorError(
                    "no pending trust mutation exists"
                ) from exc
            try:
                current = self._read_manifest()
            except FileNotFoundError:
                current = None
            allowed = {
                journal.previous_manifest_sha256,
                journal.next_manifest.manifest_sha256,
            }
            if (
                current is not None
                and current.manifest_sha256 not in allowed
            ):
                raise PhiVesselTrustOperatorError(
                    "cannot recover because manifest changed outside "
                    "the pending transaction"
                )
            _atomic_write_json(
                self.manifest_path,
                journal.next_manifest.to_dict(),
            )
            if journal.next_authority_state is not None:
                _atomic_write_json(
                    self.authority_state_path,
                    journal.next_authority_state.to_dict(),
                )
            receipt = self._receipt_for_journal(journal)
            _append_jsonl_once(self.receipt_path, receipt)
            self.journal_path.unlink()
            return receipt

    def _authority_mutation(
        self,
        *,
        permission: str,
        kind: AuthorityEventKind,
        expected_manifest_sha256: str,
        expires_at: str | None,
        observed_at: str | None,
    ) -> TrustMutationReceipt:
        permission = _require_text(
            permission,
            "permission",
            maximum=256,
        )
        expected = _require_sha256(
            expected_manifest_sha256,
            "expected_manifest_sha256",
        )
        with _exclusive_lock(self.lock_path):
            self._require_no_pending_journal()
            manifest = self._read_manifest()
            self._require_manifest_identity(manifest, expected)
            state = self._read_required_authority_state()
            self._validate_state_against_manifest(state, manifest)
            now = _canonical_time(observed_at)
            current = state.epoch(observed_at=now)
            if permission not in set(state.ceiling):
                raise PhiVesselTrustOperatorError(
                    "permission exceeds frozen authority ceiling"
                )
            active = permission in set(current.grants)
            if kind is AuthorityEventKind.GRANT and active:
                raise PhiVesselTrustOperatorError(
                    "permission is already granted"
                )
            if kind is AuthorityEventKind.REVOKE and not active:
                raise PhiVesselTrustOperatorError(
                    "permission is not currently granted"
                )
            canonical_expiry = (
                None
                if expires_at is None
                else _canonical_time(expires_at)
            )
            sequence = len(state.events)
            event_id = (
                f"trust:{sequence}:{kind.value}:"
                + _canonical_sha256(
                    {
                        "permission": permission,
                        "effective_at": now,
                        "expires_at": canonical_expiry,
                        "previous_manifest_sha256": (
                            manifest.manifest_sha256
                        ),
                    }
                )[:24]
            )
            try:
                event = AuthoritativeAuthorityEvent(
                    event_id=event_id,
                    sequence=sequence,
                    kind=kind,
                    permission=permission,
                    authority_source=self.actor_id,
                    effective_at=now,
                    expires_at=canonical_expiry,
                )
            except AuthorityProjectionError as exc:
                raise PhiVesselTrustOperatorError(
                    "authority event is invalid"
                ) from exc
            next_state = PhiVesselAuthorityState(
                principal_id=state.principal_id,
                policy_sha256=state.policy_sha256,
                ceiling=state.ceiling,
                bootstrap_manifest_sha256=(
                    state.bootstrap_manifest_sha256
                ),
                bootstrap_authority_epoch_sha256=(
                    state.bootstrap_authority_epoch_sha256
                ),
                events=state.events + (event,),
            )
            next_epoch = next_state.epoch(observed_at=now)
            next_manifest = self._manifest_with_epoch(
                manifest,
                next_epoch,
            )
            return self._commit(
                operation=(
                    "AUTHORITY_GRANT"
                    if kind is AuthorityEventKind.GRANT
                    else "AUTHORITY_REVOKE"
                ),
                previous_manifest=manifest,
                next_manifest=next_manifest,
                next_authority_state=next_state,
                authority_event_id=event.event_id,
                restart_required=False,
            )

    def _commit(
        self,
        *,
        operation: str,
        previous_manifest: PhiVesselLocalExecutionManifest,
        next_manifest: PhiVesselLocalExecutionManifest,
        next_authority_state: PhiVesselAuthorityState | None,
        authority_event_id: str | None,
        restart_required: bool,
    ) -> TrustMutationReceipt:
        journal = TrustMutationJournal(
            operation=operation,
            previous_manifest_sha256=(
                previous_manifest.manifest_sha256
            ),
            previous_authority_epoch_sha256=(
                previous_manifest.authority_epoch.authority_epoch_sha256
            ),
            next_manifest=next_manifest,
            next_authority_state=next_authority_state,
            authority_event_id=authority_event_id,
            restart_required=restart_required,
            prepared_at=_canonical_time(),
        )
        _atomic_write_json(self.journal_path, journal.to_dict())
        _atomic_write_json(
            self.manifest_path,
            next_manifest.to_dict(),
        )
        if next_authority_state is not None:
            _atomic_write_json(
                self.authority_state_path,
                next_authority_state.to_dict(),
            )
        receipt = self._receipt_for_journal(journal)
        _append_jsonl_once(self.receipt_path, receipt)
        self.journal_path.unlink()
        return receipt

    def _receipt_for_journal(
        self,
        journal: TrustMutationJournal,
    ) -> TrustMutationReceipt:
        receipt_id = (
            "trust:"
            + _canonical_sha256(
                {
                    "operation": journal.operation,
                    "previous_manifest_sha256": (
                        journal.previous_manifest_sha256
                    ),
                    "next_manifest_sha256": (
                        journal.next_manifest.manifest_sha256
                    ),
                    "authority_event_id": journal.authority_event_id,
                }
            )[:32]
        )
        return TrustMutationReceipt(
            receipt_id=receipt_id,
            operation=journal.operation,
            actor_id=self.actor_id,
            previous_manifest_sha256=(
                journal.previous_manifest_sha256
            ),
            next_manifest_sha256=(
                journal.next_manifest.manifest_sha256
            ),
            previous_authority_epoch_sha256=(
                journal.previous_authority_epoch_sha256
            ),
            next_authority_epoch_sha256=(
                journal.next_manifest.authority_epoch.authority_epoch_sha256
            ),
            authority_state_sha256=(
                None
                if journal.next_authority_state is None
                else journal.next_authority_state.authority_state_sha256
            ),
            authority_event_id=journal.authority_event_id,
            restart_required=journal.restart_required,
            applied_at=_canonical_time(),
        )

    def _read_manifest(self) -> PhiVesselLocalExecutionManifest:
        try:
            return PhiVesselLocalExecutionManifest.read(
                self.manifest_path
            )
        except PhiVesselLocalExecutionError as exc:
            raise PhiVesselTrustOperatorError(str(exc)) from exc

    def _read_required_authority_state(
        self,
    ) -> PhiVesselAuthorityState:
        try:
            return PhiVesselAuthorityState.read(
                self.authority_state_path
            )
        except FileNotFoundError as exc:
            raise PhiVesselTrustOperatorError(
                "authority event state is not initialized; run "
                "authority-bootstrap first"
            ) from exc

    def _require_manifest_identity(
        self,
        manifest: PhiVesselLocalExecutionManifest,
        expected: str,
    ) -> None:
        if manifest.manifest_sha256 != expected:
            raise PhiVesselTrustOperatorError(
                "execution manifest changed before mutation"
            )

    def _require_no_pending_journal(self) -> None:
        if self.journal_path.exists():
            raise PhiVesselTrustOperatorError(
                "pending trust mutation requires explicit recover"
            )

    def _validate_state_against_manifest(
        self,
        state: PhiVesselAuthorityState,
        manifest: PhiVesselLocalExecutionManifest,
    ) -> None:
        epoch = manifest.authority_epoch
        if state.principal_id != epoch.principal_id:
            raise PhiVesselTrustOperatorError(
                "authority state principal differs from manifest"
            )
        if state.policy_sha256 != epoch.policy_sha256:
            raise PhiVesselTrustOperatorError(
                "authority state policy differs from manifest"
            )
        if state.ceiling != epoch.ceiling:
            raise PhiVesselTrustOperatorError(
                "authority state ceiling differs from manifest"
            )
        reconstructed = state.epoch(
            observed_at=epoch.observed_at
        )
        if (
            reconstructed.authority_epoch_sha256
            != epoch.authority_epoch_sha256
        ):
            raise PhiVesselTrustOperatorError(
                "authority event state does not materialize the "
                "current manifest AuthorityEpoch"
            )

    @staticmethod
    def _manifest_with_epoch(
        manifest: PhiVesselLocalExecutionManifest,
        epoch: AuthorityEpoch,
    ) -> PhiVesselLocalExecutionManifest:
        try:
            return PhiVesselLocalExecutionManifest.build(
                enabled=manifest.enabled,
                desktop_executor_enabled=(
                    manifest.desktop_executor_enabled
                ),
                mappings=manifest.mappings,
                lease_policies=manifest.lease_policies,
                authority_epoch=epoch,
            )
        except PhiVesselLocalExecutionError as exc:
            raise PhiVesselTrustOperatorError(
                "new AuthorityEpoch violates execution manifest contract"
            ) from exc


__all__ = [
    "DEFAULT_AUTHORITY_STATE_FILENAME",
    "DEFAULT_TRUST_JOURNAL_FILENAME",
    "DEFAULT_TRUST_LOCK_FILENAME",
    "DEFAULT_TRUST_RECEIPT_FILENAME",
    "PhiVesselAuthorityState",
    "PhiVesselTrustOperator",
    "PhiVesselTrustOperatorError",
    "TrustMutationReceipt",
]
