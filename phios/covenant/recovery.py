"""Invariant-bound identity continuity and exact recovery evidence.

This module composes over Covenant CR-01 IdentitySeal. It allows PhiOS to describe
identity continuity across runtime/topology changes without treating topology,
process continuity, checkpoint possession, or recovery success as authority.

The v0.1 recovery contract is deliberately strict:
- identity equivalence is derived from named IdentitySeal fields;
- epoch continuity must advance exactly once and remain hash-linked;
- the recovered state digest must exactly match the prior recovery-state digest;
- topology may change, but topology never counts as identity evidence;
- authority never transfers merely because identity/recovery checks pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .identity import IdentitySeal, IdentitySubjectKind
from .models import (
    canonical_sha256,
    expect_exact_keys,
    expect_mapping,
    require_bool,
    require_optional_sha256,
    require_sha256,
    require_string_tuple,
    require_text,
)

IDENTITY_INVARIANT_SET_SCHEMA_VERSION = "phios.identity_invariant_set.v0.1"
FUNCTIONAL_EQUIVALENCE_RECEIPT_SCHEMA_VERSION = (
    "phios.functional_equivalence_receipt.v0.1"
)
EPOCH_BOUND_IDENTITY_SCHEMA_VERSION = "phios.epoch_bound_identity.v0.1"
RECOVERY_PATH_RECEIPT_SCHEMA_VERSION = "phios.recovery_path_receipt.v0.1"


class IdentityInvariantField(str, Enum):
    SUBJECT_ID = "subject_id"
    SUBJECT_KIND = "subject_kind"
    IMPLEMENTATION_SHA256 = "implementation_sha256"
    MANIFEST_SHA256 = "manifest_sha256"
    SOURCE_SHA256 = "source_sha256"
    ISSUER_ID = "issuer_id"
    ISSUER_KEY_ID = "issuer_key_id"


class FunctionalEquivalenceStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    CHANGED = "CHANGED"


class RecoveryStatus(str, Enum):
    RECOVERED = "RECOVERED"
    BLOCKED = "BLOCKED"


def _require_epoch(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _field_value(seal: IdentitySeal, field: IdentityInvariantField) -> str:
    if field is IdentityInvariantField.SUBJECT_ID:
        return seal.subject_id
    if field is IdentityInvariantField.SUBJECT_KIND:
        return seal.subject_kind.value
    if field is IdentityInvariantField.IMPLEMENTATION_SHA256:
        return seal.implementation_sha256
    if field is IdentityInvariantField.MANIFEST_SHA256:
        return seal.manifest_sha256
    if field is IdentityInvariantField.SOURCE_SHA256:
        return seal.source_sha256
    if field is IdentityInvariantField.ISSUER_ID:
        return seal.issuer_id
    if field is IdentityInvariantField.ISSUER_KEY_ID:
        return seal.issuer_key_id
    raise ValueError(f"unsupported identity invariant field: {field}")


@dataclass(frozen=True, slots=True)
class IdentityInvariantSet:
    """Declare the exact IdentitySeal fields required for equivalence."""

    invariant_set_id: str
    version: str
    required_fields: tuple[IdentityInvariantField, ...]
    topology_is_identity_evidence: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = IDENTITY_INVARIANT_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != IDENTITY_INVARIANT_SET_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported identity invariant schema: {self.schema_version}"
            )
        require_text(self.invariant_set_id, "invariant_set_id", maximum=128)
        require_text(self.version, "version", maximum=64)
        if not self.required_fields:
            raise ValueError("required_fields must not be empty")
        if any(
            not isinstance(field, IdentityInvariantField)
            for field in self.required_fields
        ):
            raise ValueError(
                "required_fields must contain supported IdentityInvariantField values"
            )
        values = tuple(field.value for field in self.required_fields)
        if tuple(sorted(values)) != values:
            raise ValueError("required_fields must be sorted")
        if len(set(values)) != len(values):
            raise ValueError("required_fields must not contain duplicates")
        required_minimum = {
            IdentityInvariantField.SUBJECT_ID,
            IdentityInvariantField.SUBJECT_KIND,
        }
        if not required_minimum.issubset(set(self.required_fields)):
            raise ValueError(
                "identity invariant set must include subject_id and subject_kind"
            )
        if self.topology_is_identity_evidence is not False:
            raise ValueError(
                "topology cannot be used as identity evidence in this contract"
            )
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError(
                "identity invariant set cannot carry action or execution authority"
            )

    @classmethod
    def strict_cr01(cls) -> "IdentityInvariantSet":
        fields = tuple(
            sorted(
                IdentityInvariantField,
                key=lambda item: item.value,
            )
        )
        return cls(
            invariant_set_id="covenant.cr01.strict-identity",
            version="0.1",
            required_fields=fields,
        )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "invariant_set_id": self.invariant_set_id,
            "version": self.version,
            "required_fields": [field.value for field in self.required_fields],
            "topology_is_identity_evidence": self.topology_is_identity_evidence,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["invariant_set_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "IdentityInvariantSet":
        data = expect_mapping(value, "identity invariant set")
        expect_exact_keys(
            data,
            {
                "schema_version",
                "invariant_set_id",
                "version",
                "required_fields",
                "topology_is_identity_evidence",
                "action_authority",
                "execution_authority",
                "invariant_set_sha256",
            },
            "identity invariant set",
        )
        raw_fields = require_string_tuple(
            data["required_fields"],
            "required_fields",
            maximum_items=len(IdentityInvariantField),
            maximum_text=64,
        )
        try:
            fields = tuple(IdentityInvariantField(item) for item in raw_fields)
        except ValueError as exc:
            raise ValueError(
                "identity invariant set contains unsupported required field"
            ) from exc
        result = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            invariant_set_id=require_text(
                data["invariant_set_id"],
                "invariant_set_id",
                maximum=128,
            ),
            version=require_text(data["version"], "version", maximum=64),
            required_fields=fields,
            topology_is_identity_evidence=require_bool(
                data["topology_is_identity_evidence"],
                "topology_is_identity_evidence",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["invariant_set_sha256"] != result.sha256():
            raise ValueError(
                "identity invariant set digest does not match canonical contract"
            )
        return result


@dataclass(frozen=True, slots=True)
class FunctionalEquivalenceReceipt:
    """Compare two exact IdentitySeal records under one invariant set."""

    status: FunctionalEquivalenceStatus
    invariant_set_sha256: str
    previous_identity_seal_sha256: str
    candidate_identity_seal_sha256: str
    matched_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    topology_evidence_used: bool = False
    trusted_identity: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = FUNCTIONAL_EQUIVALENCE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FUNCTIONAL_EQUIVALENCE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported functional equivalence receipt schema"
            )
        if not isinstance(self.status, FunctionalEquivalenceStatus):
            raise ValueError(
                "status must be a supported FunctionalEquivalenceStatus"
            )
        require_sha256(self.invariant_set_sha256, "invariant_set_sha256")
        require_sha256(
            self.previous_identity_seal_sha256,
            "previous_identity_seal_sha256",
        )
        require_sha256(
            self.candidate_identity_seal_sha256,
            "candidate_identity_seal_sha256",
        )
        for label, values in (
            ("matched_fields", self.matched_fields),
            ("mismatched_fields", self.mismatched_fields),
        ):
            if tuple(sorted(values)) != values:
                raise ValueError(f"{label} must be sorted")
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must not contain duplicates")
            for item in values:
                IdentityInvariantField(item)
        if set(self.matched_fields) & set(self.mismatched_fields):
            raise ValueError(
                "matched_fields and mismatched_fields must not overlap"
            )
        if self.status is FunctionalEquivalenceStatus.EQUIVALENT:
            if self.mismatched_fields:
                raise ValueError(
                    "EQUIVALENT receipt cannot contain mismatched_fields"
                )
        elif not self.mismatched_fields:
            raise ValueError("CHANGED receipt requires mismatched_fields")
        if self.topology_evidence_used is not False:
            raise ValueError(
                "functional equivalence cannot use topology as identity evidence"
            )
        if self.trusted_identity is not False:
            raise ValueError(
                "functional equivalence receipt cannot establish trusted identity"
            )
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError(
                "functional equivalence receipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "invariant_set_sha256": self.invariant_set_sha256,
            "previous_identity_seal_sha256": self.previous_identity_seal_sha256,
            "candidate_identity_seal_sha256": self.candidate_identity_seal_sha256,
            "matched_fields": list(self.matched_fields),
            "mismatched_fields": list(self.mismatched_fields),
            "topology_evidence_used": self.topology_evidence_used,
            "trusted_identity": self.trusted_identity,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "FunctionalEquivalenceReceipt":
        data = expect_mapping(value, "functional equivalence receipt")
        expect_exact_keys(
            data,
            {
                "schema_version",
                "status",
                "invariant_set_sha256",
                "previous_identity_seal_sha256",
                "candidate_identity_seal_sha256",
                "matched_fields",
                "mismatched_fields",
                "topology_evidence_used",
                "trusted_identity",
                "action_authority",
                "execution_authority",
                "receipt_sha256",
            },
            "functional equivalence receipt",
        )
        try:
            status = FunctionalEquivalenceStatus(
                require_text(data["status"], "status", maximum=16)
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported functional equivalence status: {data['status']}"
            ) from exc
        receipt = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            status=status,
            invariant_set_sha256=require_sha256(
                data["invariant_set_sha256"],
                "invariant_set_sha256",
            ),
            previous_identity_seal_sha256=require_sha256(
                data["previous_identity_seal_sha256"],
                "previous_identity_seal_sha256",
            ),
            candidate_identity_seal_sha256=require_sha256(
                data["candidate_identity_seal_sha256"],
                "candidate_identity_seal_sha256",
            ),
            matched_fields=require_string_tuple(
                data["matched_fields"],
                "matched_fields",
                maximum_items=len(IdentityInvariantField),
                maximum_text=64,
            ),
            mismatched_fields=require_string_tuple(
                data["mismatched_fields"],
                "mismatched_fields",
                maximum_items=len(IdentityInvariantField),
                maximum_text=64,
            ),
            topology_evidence_used=require_bool(
                data["topology_evidence_used"],
                "topology_evidence_used",
            ),
            trusted_identity=require_bool(
                data["trusted_identity"],
                "trusted_identity",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "functional equivalence receipt digest does not match canonical receipt"
            )
        return receipt


def evaluate_functional_equivalence(
    previous: IdentitySeal,
    candidate: IdentitySeal,
    invariant_set: IdentityInvariantSet,
) -> FunctionalEquivalenceReceipt:
    matched: list[str] = []
    mismatched: list[str] = []
    for field in invariant_set.required_fields:
        if _field_value(previous, field) == _field_value(candidate, field):
            matched.append(field.value)
        else:
            mismatched.append(field.value)
    status = (
        FunctionalEquivalenceStatus.EQUIVALENT
        if not mismatched
        else FunctionalEquivalenceStatus.CHANGED
    )
    return FunctionalEquivalenceReceipt(
        status=status,
        invariant_set_sha256=invariant_set.sha256(),
        previous_identity_seal_sha256=previous.sha256(),
        candidate_identity_seal_sha256=candidate.sha256(),
        matched_fields=tuple(sorted(matched)),
        mismatched_fields=tuple(sorted(mismatched)),
        topology_evidence_used=False,
        trusted_identity=False,
        action_authority=False,
        execution_authority=False,
    )


@dataclass(frozen=True, slots=True)
class EpochBoundIdentity:
    """Bind one identity seal to one recovery epoch and runtime topology snapshot."""

    subject_id: str
    subject_kind: IdentitySubjectKind
    epoch: int
    identity_seal_sha256: str
    invariant_set_sha256: str
    topology_sha256: str
    recovery_state_sha256: str
    previous_epoch_identity_sha256: str | None = None
    recovery_checkpoint_sha256: str | None = None
    trusted_identity: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = EPOCH_BOUND_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EPOCH_BOUND_IDENTITY_SCHEMA_VERSION:
            raise ValueError(f"unsupported epoch-bound identity schema: {self.schema_version}")
        require_text(self.subject_id, "subject_id", maximum=128)
        if not isinstance(self.subject_kind, IdentitySubjectKind):
            raise ValueError("subject_kind must be a supported IdentitySubjectKind")
        _require_epoch(self.epoch, "epoch")
        require_sha256(self.identity_seal_sha256, "identity_seal_sha256")
        require_sha256(self.invariant_set_sha256, "invariant_set_sha256")
        require_sha256(self.topology_sha256, "topology_sha256")
        require_sha256(self.recovery_state_sha256, "recovery_state_sha256")
        require_optional_sha256(
            self.previous_epoch_identity_sha256,
            "previous_epoch_identity_sha256",
        )
        require_optional_sha256(
            self.recovery_checkpoint_sha256,
            "recovery_checkpoint_sha256",
        )
        if self.epoch == 0:
            if (
                self.previous_epoch_identity_sha256 is not None
                or self.recovery_checkpoint_sha256 is not None
            ):
                raise ValueError(
                    "epoch 0 cannot claim a prior epoch or recovery checkpoint"
                )
        else:
            if self.previous_epoch_identity_sha256 is None:
                raise ValueError(
                    "recovered epoch requires previous_epoch_identity_sha256"
                )
            if self.recovery_checkpoint_sha256 is None:
                raise ValueError(
                    "recovered epoch requires recovery_checkpoint_sha256"
                )
        if self.trusted_identity is not False:
            raise ValueError(
                "epoch-bound identity cannot establish trusted identity"
            )
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError("epoch-bound identity cannot carry authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "epoch": self.epoch,
            "identity_seal_sha256": self.identity_seal_sha256,
            "invariant_set_sha256": self.invariant_set_sha256,
            "topology_sha256": self.topology_sha256,
            "recovery_state_sha256": self.recovery_state_sha256,
            "previous_epoch_identity_sha256": self.previous_epoch_identity_sha256,
            "recovery_checkpoint_sha256": self.recovery_checkpoint_sha256,
            "trusted_identity": self.trusted_identity,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["epoch_identity_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "EpochBoundIdentity":
        data = expect_mapping(value, "epoch-bound identity")
        expect_exact_keys(
            data,
            {
                "schema_version",
                "subject_id",
                "subject_kind",
                "epoch",
                "identity_seal_sha256",
                "invariant_set_sha256",
                "topology_sha256",
                "recovery_state_sha256",
                "previous_epoch_identity_sha256",
                "recovery_checkpoint_sha256",
                "trusted_identity",
                "action_authority",
                "execution_authority",
                "epoch_identity_sha256",
            },
            "epoch-bound identity",
        )
        try:
            subject_kind = IdentitySubjectKind(
                require_text(
                    data["subject_kind"],
                    "subject_kind",
                    maximum=32,
                )
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported identity subject kind: {data['subject_kind']}"
            ) from exc
        identity = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            subject_id=require_text(
                data["subject_id"],
                "subject_id",
                maximum=128,
            ),
            subject_kind=subject_kind,
            epoch=_require_epoch(data["epoch"], "epoch"),
            identity_seal_sha256=require_sha256(
                data["identity_seal_sha256"],
                "identity_seal_sha256",
            ),
            invariant_set_sha256=require_sha256(
                data["invariant_set_sha256"],
                "invariant_set_sha256",
            ),
            topology_sha256=require_sha256(
                data["topology_sha256"],
                "topology_sha256",
            ),
            recovery_state_sha256=require_sha256(
                data["recovery_state_sha256"],
                "recovery_state_sha256",
            ),
            previous_epoch_identity_sha256=require_optional_sha256(
                data["previous_epoch_identity_sha256"],
                "previous_epoch_identity_sha256",
            ),
            recovery_checkpoint_sha256=require_optional_sha256(
                data["recovery_checkpoint_sha256"],
                "recovery_checkpoint_sha256",
            ),
            trusted_identity=require_bool(
                data["trusted_identity"],
                "trusted_identity",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["epoch_identity_sha256"] != identity.sha256():
            raise ValueError(
                "epoch-bound identity digest does not match canonical identity"
            )
        return identity


@dataclass(frozen=True, slots=True)
class RecoveryPathReceipt:
    """Record exact recovery continuity without transferring authority."""

    status: RecoveryStatus
    previous_epoch_identity_sha256: str
    recovered_epoch_identity_sha256: str
    functional_equivalence_receipt_sha256: str
    recovery_checkpoint_sha256: str
    previous_epoch: int
    recovered_epoch: int
    previous_topology_sha256: str
    recovered_topology_sha256: str
    previous_state_sha256: str
    recovered_state_sha256: str
    topology_changed: bool
    seal_bindings_valid: bool
    invariant_set_bound: bool
    subject_bindings_valid: bool
    epoch_chain_linked: bool
    checkpoint_bound: bool
    epoch_advanced: bool
    identity_equivalent: bool
    state_recovered_exactly: bool
    reason: str
    authority_inherited: bool = False
    authority_revalidation_required: bool = True
    trusted_identity: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = RECOVERY_PATH_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RECOVERY_PATH_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported recovery path receipt schema")
        if not isinstance(self.status, RecoveryStatus):
            raise ValueError("status must be a supported RecoveryStatus")
        for label, digest_value in (
            (
                "previous_epoch_identity_sha256",
                self.previous_epoch_identity_sha256,
            ),
            (
                "recovered_epoch_identity_sha256",
                self.recovered_epoch_identity_sha256,
            ),
            (
                "functional_equivalence_receipt_sha256",
                self.functional_equivalence_receipt_sha256,
            ),
            ("recovery_checkpoint_sha256", self.recovery_checkpoint_sha256),
            ("previous_topology_sha256", self.previous_topology_sha256),
            ("recovered_topology_sha256", self.recovered_topology_sha256),
            ("previous_state_sha256", self.previous_state_sha256),
            ("recovered_state_sha256", self.recovered_state_sha256),
        ):
            require_sha256(digest_value, label)
        _require_epoch(self.previous_epoch, "previous_epoch")
        _require_epoch(self.recovered_epoch, "recovered_epoch")
        require_text(self.reason, "reason", maximum=512)
        for label, bool_value in (
            ("topology_changed", self.topology_changed),
            ("seal_bindings_valid", self.seal_bindings_valid),
            ("invariant_set_bound", self.invariant_set_bound),
            ("subject_bindings_valid", self.subject_bindings_valid),
            ("epoch_chain_linked", self.epoch_chain_linked),
            ("checkpoint_bound", self.checkpoint_bound),
            ("epoch_advanced", self.epoch_advanced),
            ("identity_equivalent", self.identity_equivalent),
            ("state_recovered_exactly", self.state_recovered_exactly),
            ("authority_inherited", self.authority_inherited),
            (
                "authority_revalidation_required",
                self.authority_revalidation_required,
            ),
            ("trusted_identity", self.trusted_identity),
            ("action_authority", self.action_authority),
            ("execution_authority", self.execution_authority),
        ):
            require_bool(bool_value, label)
        if self.topology_changed != (
            self.previous_topology_sha256 != self.recovered_topology_sha256
        ):
            raise ValueError("topology_changed does not match topology digests")
        if self.epoch_advanced != (self.recovered_epoch == self.previous_epoch + 1):
            raise ValueError("epoch_advanced does not match epoch values")
        if self.state_recovered_exactly != (
            self.previous_state_sha256 == self.recovered_state_sha256
        ):
            raise ValueError(
                "state_recovered_exactly does not match recovery-state digests"
            )
        success = (
            self.seal_bindings_valid
            and self.invariant_set_bound
            and self.subject_bindings_valid
            and self.epoch_chain_linked
            and self.checkpoint_bound
            and self.epoch_advanced
            and self.identity_equivalent
            and self.state_recovered_exactly
        )
        if self.status is RecoveryStatus.RECOVERED and not success:
            raise ValueError(
                "RECOVERED requires exact epoch, identity, and state continuity"
            )
        if self.status is RecoveryStatus.BLOCKED and success:
            raise ValueError("BLOCKED cannot claim all recovery requirements satisfied")
        if self.authority_inherited is not False:
            raise ValueError("recovery cannot inherit authority across epochs")
        if self.authority_revalidation_required is not True:
            raise ValueError(
                "recovery must require downstream authority revalidation"
            )
        if self.trusted_identity is not False:
            raise ValueError("recovery receipt cannot establish trusted identity")
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError("recovery receipt cannot carry authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "previous_epoch_identity_sha256": self.previous_epoch_identity_sha256,
            "recovered_epoch_identity_sha256": self.recovered_epoch_identity_sha256,
            "functional_equivalence_receipt_sha256": (
                self.functional_equivalence_receipt_sha256
            ),
            "recovery_checkpoint_sha256": self.recovery_checkpoint_sha256,
            "previous_epoch": self.previous_epoch,
            "recovered_epoch": self.recovered_epoch,
            "previous_topology_sha256": self.previous_topology_sha256,
            "recovered_topology_sha256": self.recovered_topology_sha256,
            "previous_state_sha256": self.previous_state_sha256,
            "recovered_state_sha256": self.recovered_state_sha256,
            "topology_changed": self.topology_changed,
            "seal_bindings_valid": self.seal_bindings_valid,
            "invariant_set_bound": self.invariant_set_bound,
            "subject_bindings_valid": self.subject_bindings_valid,
            "epoch_chain_linked": self.epoch_chain_linked,
            "checkpoint_bound": self.checkpoint_bound,
            "epoch_advanced": self.epoch_advanced,
            "identity_equivalent": self.identity_equivalent,
            "state_recovered_exactly": self.state_recovered_exactly,
            "reason": self.reason,
            "authority_inherited": self.authority_inherited,
            "authority_revalidation_required": self.authority_revalidation_required,
            "trusted_identity": self.trusted_identity,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "RecoveryPathReceipt":
        data = expect_mapping(value, "recovery path receipt")
        expect_exact_keys(
            data,
            {
                "schema_version",
                "status",
                "previous_epoch_identity_sha256",
                "recovered_epoch_identity_sha256",
                "functional_equivalence_receipt_sha256",
                "recovery_checkpoint_sha256",
                "previous_epoch",
                "recovered_epoch",
                "previous_topology_sha256",
                "recovered_topology_sha256",
                "previous_state_sha256",
                "recovered_state_sha256",
                "topology_changed",
                "seal_bindings_valid",
                "invariant_set_bound",
                "subject_bindings_valid",
                "epoch_chain_linked",
                "checkpoint_bound",
                "epoch_advanced",
                "identity_equivalent",
                "state_recovered_exactly",
                "reason",
                "authority_inherited",
                "authority_revalidation_required",
                "trusted_identity",
                "action_authority",
                "execution_authority",
                "receipt_sha256",
            },
            "recovery path receipt",
        )
        try:
            status = RecoveryStatus(
                require_text(data["status"], "status", maximum=16)
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported recovery status: {data['status']}"
            ) from exc
        receipt = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            status=status,
            previous_epoch_identity_sha256=require_sha256(
                data["previous_epoch_identity_sha256"],
                "previous_epoch_identity_sha256",
            ),
            recovered_epoch_identity_sha256=require_sha256(
                data["recovered_epoch_identity_sha256"],
                "recovered_epoch_identity_sha256",
            ),
            functional_equivalence_receipt_sha256=require_sha256(
                data["functional_equivalence_receipt_sha256"],
                "functional_equivalence_receipt_sha256",
            ),
            recovery_checkpoint_sha256=require_sha256(
                data["recovery_checkpoint_sha256"],
                "recovery_checkpoint_sha256",
            ),
            previous_epoch=_require_epoch(
                data["previous_epoch"],
                "previous_epoch",
            ),
            recovered_epoch=_require_epoch(
                data["recovered_epoch"],
                "recovered_epoch",
            ),
            previous_topology_sha256=require_sha256(
                data["previous_topology_sha256"],
                "previous_topology_sha256",
            ),
            recovered_topology_sha256=require_sha256(
                data["recovered_topology_sha256"],
                "recovered_topology_sha256",
            ),
            previous_state_sha256=require_sha256(
                data["previous_state_sha256"],
                "previous_state_sha256",
            ),
            recovered_state_sha256=require_sha256(
                data["recovered_state_sha256"],
                "recovered_state_sha256",
            ),
            topology_changed=require_bool(
                data["topology_changed"],
                "topology_changed",
            ),
            seal_bindings_valid=require_bool(
                data["seal_bindings_valid"],
                "seal_bindings_valid",
            ),
            invariant_set_bound=require_bool(
                data["invariant_set_bound"],
                "invariant_set_bound",
            ),
            subject_bindings_valid=require_bool(
                data["subject_bindings_valid"],
                "subject_bindings_valid",
            ),
            epoch_chain_linked=require_bool(
                data["epoch_chain_linked"],
                "epoch_chain_linked",
            ),
            checkpoint_bound=require_bool(
                data["checkpoint_bound"],
                "checkpoint_bound",
            ),
            epoch_advanced=require_bool(
                data["epoch_advanced"],
                "epoch_advanced",
            ),
            identity_equivalent=require_bool(
                data["identity_equivalent"],
                "identity_equivalent",
            ),
            state_recovered_exactly=require_bool(
                data["state_recovered_exactly"],
                "state_recovered_exactly",
            ),
            reason=require_text(data["reason"], "reason", maximum=512),
            authority_inherited=require_bool(
                data["authority_inherited"],
                "authority_inherited",
            ),
            authority_revalidation_required=require_bool(
                data["authority_revalidation_required"],
                "authority_revalidation_required",
            ),
            trusted_identity=require_bool(
                data["trusted_identity"],
                "trusted_identity",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["receipt_sha256"] != receipt.sha256():
            raise ValueError(
                "recovery path receipt digest does not match canonical receipt"
            )
        return receipt


class RecoveryEvaluator:
    """Evaluate one exact epoch-to-epoch recovery attempt."""

    def __init__(self, invariant_set: IdentityInvariantSet) -> None:
        self.invariant_set = invariant_set

    def assess(
        self,
        *,
        previous_identity: EpochBoundIdentity,
        recovered_identity: EpochBoundIdentity,
        previous_seal: IdentitySeal,
        recovered_seal: IdentitySeal,
        recovery_checkpoint_sha256: str,
    ) -> tuple[FunctionalEquivalenceReceipt, RecoveryPathReceipt]:
        checkpoint = require_sha256(
            recovery_checkpoint_sha256,
            "recovery_checkpoint_sha256",
        )
        equivalence = evaluate_functional_equivalence(
            previous_seal,
            recovered_seal,
            self.invariant_set,
        )
        identity_equivalent = (
            equivalence.status is FunctionalEquivalenceStatus.EQUIVALENT
        )
        epoch_advanced = recovered_identity.epoch == previous_identity.epoch + 1
        state_exact = (
            previous_identity.recovery_state_sha256
            == recovered_identity.recovery_state_sha256
        )
        topology_changed = (
            previous_identity.topology_sha256
            != recovered_identity.topology_sha256
        )
        seal_bindings_valid = (
            previous_identity.identity_seal_sha256 == previous_seal.sha256()
            and recovered_identity.identity_seal_sha256 == recovered_seal.sha256()
        )
        invariant_set_bound = (
            previous_identity.invariant_set_sha256 == self.invariant_set.sha256()
            and recovered_identity.invariant_set_sha256
            == self.invariant_set.sha256()
        )
        subject_bindings_valid = (
            previous_identity.subject_id == previous_seal.subject_id
            and recovered_identity.subject_id == recovered_seal.subject_id
            and previous_identity.subject_kind == previous_seal.subject_kind
            and recovered_identity.subject_kind == recovered_seal.subject_kind
        )
        epoch_chain_linked = (
            recovered_identity.previous_epoch_identity_sha256
            == previous_identity.sha256()
        )
        checkpoint_bound = (
            recovered_identity.recovery_checkpoint_sha256 == checkpoint
        )

        reason = "recovery_requirements_satisfied"
        if not seal_bindings_valid:
            reason = "identity_seal_binding_mismatch"
        elif not invariant_set_bound:
            reason = "identity_invariant_set_mismatch"
        elif not subject_bindings_valid:
            reason = "subject_identity_binding_mismatch"
        elif not epoch_chain_linked:
            reason = "recovery_epoch_chain_mismatch"
        elif not checkpoint_bound:
            reason = "recovery_checkpoint_mismatch"
        elif not epoch_advanced:
            reason = "recovery_epoch_not_exactly_next"
        elif not identity_equivalent:
            reason = "identity_invariants_changed"
        elif not state_exact:
            reason = "recovery_state_digest_changed"

        status = (
            RecoveryStatus.RECOVERED
            if reason == "recovery_requirements_satisfied"
            else RecoveryStatus.BLOCKED
        )
        receipt = RecoveryPathReceipt(
            status=status,
            previous_epoch_identity_sha256=previous_identity.sha256(),
            recovered_epoch_identity_sha256=recovered_identity.sha256(),
            functional_equivalence_receipt_sha256=equivalence.sha256(),
            recovery_checkpoint_sha256=checkpoint,
            previous_epoch=previous_identity.epoch,
            recovered_epoch=recovered_identity.epoch,
            previous_topology_sha256=previous_identity.topology_sha256,
            recovered_topology_sha256=recovered_identity.topology_sha256,
            previous_state_sha256=previous_identity.recovery_state_sha256,
            recovered_state_sha256=recovered_identity.recovery_state_sha256,
            topology_changed=topology_changed,
            seal_bindings_valid=seal_bindings_valid,
            invariant_set_bound=invariant_set_bound,
            subject_bindings_valid=subject_bindings_valid,
            epoch_chain_linked=epoch_chain_linked,
            checkpoint_bound=checkpoint_bound,
            epoch_advanced=epoch_advanced,
            identity_equivalent=identity_equivalent,
            state_recovered_exactly=state_exact,
            reason=reason,
            authority_inherited=False,
            authority_revalidation_required=True,
            trusted_identity=False,
            action_authority=False,
            execution_authority=False,
        )
        return equivalence, receipt
