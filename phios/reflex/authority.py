"""PhiReflex v0.8 authenticated authority provenance and revocation.

Ed25519 signatures authenticate possession of a locally trusted public key.
Trust-anchor installation remains an explicit local root-of-trust action.
Signed authority never grants action or execution permission.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from phios.reflex.control_plane import (
    ReflexRuntimeControlPlane,
    activation_grant_from_payload,
)
from phios.reflex.coordination import runtime_locked
from phios.reflex.models import ReflexInput
from phios.reflex.providers.base import ReflexProvider
from phios.reflex.runtime_influence import (
    ReflexActivationGrant,
    ReflexActivationRequest,
    ReflexRoutingInfluenceSignal,
)


PURPOSE_ACTIVATION_GRANT = "activation_grant"
PURPOSE_GRANT_REVOCATION = "grant_revocation"
PURPOSE_TRUST_TRANSITION = "trust_transition"
PURPOSE_LEDGER_CHECKPOINT = "ledger_checkpoint"
PURPOSE_GRANT_USE_POLICY = "grant_use_policy"
PURPOSE_PROVIDER_MANIFEST = "provider_manifest"
PURPOSE_LEASE_RENEWAL = "lease_renewal"
ALLOWED_PURPOSES = (
    PURPOSE_ACTIVATION_GRANT,
    PURPOSE_GRANT_REVOCATION,
    PURPOSE_TRUST_TRANSITION,
    PURPOSE_LEDGER_CHECKPOINT,
    PURPOSE_GRANT_USE_POLICY,
    PURPOSE_PROVIDER_MANIFEST,
    PURPOSE_LEASE_RENEWAL,
)


class ReflexAuthorityContractError(ValueError):
    """Raised when signed authority provenance is malformed or untrusted."""


@dataclass(frozen=True, slots=True)
class ReflexAuthorityTrustAnchor:
    schema: str
    issuer_id: str
    key_id: str
    algorithm: str
    public_key_b64: str
    allowed_purposes: tuple[str, ...]
    anchor_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "issuer_id": self.issuer_id,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "public_key_b64": self.public_key_b64,
            "allowed_purposes": list(self.allowed_purposes),
            "anchor_sha256": self.anchor_sha256,
        }


@dataclass(frozen=True, slots=True)
class SignedActivationGrantEnvelope:
    schema: str
    issuer_id: str
    key_id: str
    issued_at_epoch: int
    valid_from_epoch: int
    valid_until_epoch: int | None
    grant: ReflexActivationGrant
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return activation_grant_signature_payload(
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            issued_at_epoch=self.issued_at_epoch,
            valid_from_epoch=self.valid_from_epoch,
            valid_until_epoch=self.valid_until_epoch,
            grant=self.grant,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexGrantRevocation:
    schema: str
    revocation_id: str
    issuer_id: str
    key_id: str
    target_grant_sha256: str
    effective_epoch: int
    reason: str
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return grant_revocation_signature_payload(
            revocation_id=self.revocation_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            target_grant_sha256=self.target_grant_sha256,
            effective_epoch=self.effective_epoch,
            reason=self.reason,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexAuthorityReceipt:
    schema: str
    status: str
    reason: str
    evaluation_epoch: int
    issuer_id: str | None
    key_id: str | None
    grant_sha256: str | None
    related_sha256: str | None
    authenticated: bool
    trust_boundary_expanded: bool
    routing_influence_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "evaluation_epoch": self.evaluation_epoch,
            "issuer_id": self.issuer_id,
            "key_id": self.key_id,
            "grant_sha256": self.grant_sha256,
            "related_sha256": self.related_sha256,
            "authenticated": self.authenticated,
            "trust_boundary_expanded": self.trust_boundary_expanded,
            "routing_influence_authority": self.routing_influence_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class ReflexAuthorityPlane:
    """Authenticated authority wrapper around the v0.7 runtime control plane."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        control: ReflexRuntimeControlPlane | None = None,
    ) -> None:
        self.control = control or ReflexRuntimeControlPlane(root=root)
        self.root = self.control.root / "authority"
        self._runtime_lock = self.control._runtime_lock

    @property
    def trust_dir(self) -> Path:
        return self.root / "trust"

    @property
    def signed_grants_dir(self) -> Path:
        return self.root / "signed-grants"

    @property
    def revocations_dir(self) -> Path:
        return self.root / "revocations"

    @runtime_locked
    def verify_signed_payload(
        self,
        *,
        issuer_id: str,
        key_id: str,
        purpose: str,
        payload: Mapping[str, Any],
        signature_b64: str,
    ) -> str:
        """Verify a canonical payload under an explicitly trusted purpose."""

        if purpose not in ALLOWED_PURPOSES:
            raise ReflexAuthorityContractError(
                "unsupported authenticated authority purpose"
            )
        trusted = self._require_anchor(issuer_id, key_id)
        if purpose not in trusted.allowed_purposes:
            raise ReflexAuthorityContractError(
                "trusted key is not allowed for requested authority purpose"
            )
        _verify_ed25519(
            trusted.public_key_b64,
            canonical_authority_bytes(dict(payload)),
            signature_b64,
        )
        return trusted.anchor_sha256

    @runtime_locked
    def require_trust_anchor(
        self,
        *,
        issuer_id: str,
        key_id: str,
    ) -> ReflexAuthorityTrustAnchor:
        """Return one validated local trust anchor."""

        return self._require_anchor(issuer_id, key_id)

    @runtime_locked
    def find_signed_grant_by_sha256(
        self,
        grant_sha256: str,
    ) -> SignedActivationGrantEnvelope | None:
        """Return an authenticated-grant envelope by exact v0.6 grant digest."""

        _require_sha256(grant_sha256, "grant_sha256")
        return self._find_signed_grant_by_sha(grant_sha256)

    @runtime_locked
    def status(self, *, evaluation_epoch: int) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        control_status = self.control.status(evaluation_epoch=epoch)
        try:
            enforcement = self._enforce_active_authority(epoch)
            if enforcement is not None:
                control_status = self.control.status(evaluation_epoch=epoch)
            anchors = self._list_anchors()
            grants = self._list_signed_grants()
            revocations = self._list_revocations()
        except ReflexAuthorityContractError:
            if control_status.get("routing_influence_active") is True:
                self.control.deactivate(
                    reason="authority_provenance_invalid_fail_closed",
                    evaluation_epoch=epoch,
                )
            raise
        return {
            "ok": True,
            "evaluation_epoch": epoch,
            "control_sha256": self._control_sha(
                control_status,
                anchors=anchors,
                grants=grants,
                revocations=revocations,
            ),
            "authenticated_authority_enforcement": enforcement,
            "routing_influence_active": control_status.get(
                "routing_influence_active", False
            ),
            "control": control_status,
            "trust_anchors": [item.to_dict() for item in anchors],
            "signed_grants": [item.to_dict() for item in grants],
            "revocations": [item.to_dict() for item in revocations],
        }

    @runtime_locked
    def ingest_trust_anchor(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._assert_control_sha(expected_control_sha256, epoch)
        anchor = trust_anchor_from_payload(payload)
        _validate_trust_anchor(anchor)
        path = self._anchor_path(anchor.issuer_id, anchor.key_id)
        if path.exists():
            existing = trust_anchor_from_payload(_read_object(path))
            _validate_trust_anchor(existing)
            if existing.anchor_sha256 != anchor.anchor_sha256:
                raise ReflexAuthorityContractError(
                    "issuer/key trust anchor already exists with different contents"
                )
            receipt = self._receipt(
                status="TRUST_ANCHOR_ALREADY_PRESENT",
                reason="exact_local_root_of_trust_already_configured",
                evaluation_epoch=epoch,
                issuer_id=anchor.issuer_id,
                key_id=anchor.key_id,
                grant_sha256=None,
                related_sha=anchor.anchor_sha256,
                authenticated=False,
                trust_boundary_expanded=False,
            )
            self.control.append_audit_receipt(
                kind="authority",
                evaluation_epoch=epoch,
                receipt=receipt.to_dict(),
            )
            return {
                "ok": True,
                "idempotent": True,
                "anchor": anchor.to_dict(),
                "receipt": receipt.to_dict(),
            }

        _atomic_write_json(path, anchor.to_dict())
        receipt = self._receipt(
            status="TRUST_ANCHOR_INGESTED",
            reason="explicit_local_root_of_trust_configured",
            evaluation_epoch=epoch,
            issuer_id=anchor.issuer_id,
            key_id=anchor.key_id,
            grant_sha256=None,
            related_sha=anchor.anchor_sha256,
            authenticated=False,
            trust_boundary_expanded=True,
        )
        self.control.append_audit_receipt(
            kind="authority",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "idempotent": False,
            "anchor": anchor.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def ingest_signed_grant(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._assert_control_sha(expected_control_sha256, epoch)
        envelope = signed_activation_grant_from_payload(payload)
        self._verify_signed_grant(envelope, evaluation_epoch=epoch)
        path = self.signed_grants_dir / f"{_safe_id(envelope.grant.grant_id)}.json"
        if path.exists():
            existing = signed_activation_grant_from_payload(_read_object(path))
            if existing.envelope_sha256 != envelope.envelope_sha256:
                raise ReflexAuthorityContractError(
                    "signed grant_id already exists with different envelope"
                )
            receipt = self._receipt(
                status="SIGNED_GRANT_ALREADY_PRESENT",
                reason="exact_authenticated_grant_already_ingested",
                evaluation_epoch=epoch,
                issuer_id=envelope.issuer_id,
                key_id=envelope.key_id,
                grant_sha256=envelope.grant.grant_sha256,
                related_sha=envelope.envelope_sha256,
                authenticated=True,
                trust_boundary_expanded=False,
            )
            self.control.append_audit_receipt(
                kind="authority",
                evaluation_epoch=epoch,
                receipt=receipt.to_dict(),
            )
            return {
                "ok": True,
                "idempotent": True,
                "envelope": envelope.to_dict(),
                "receipt": receipt.to_dict(),
            }

        control_result = self.control.ingest_grant_payload(
            envelope.grant.to_payload(),
            evaluation_epoch=epoch,
        )
        # The underlying v0.6 grant is inert under v0.8 unless this verified
        # envelope is present. Persisting it first therefore fails closed if
        # the authenticated-envelope write itself cannot complete.
        _atomic_write_json(path, envelope.to_dict())
        receipt = self._receipt(
            status="SIGNED_GRANT_INGESTED",
            reason="ed25519_authenticated_activation_grant_persisted",
            evaluation_epoch=epoch,
            issuer_id=envelope.issuer_id,
            key_id=envelope.key_id,
            grant_sha256=envelope.grant.grant_sha256,
            related_sha=envelope.envelope_sha256,
            authenticated=True,
            trust_boundary_expanded=False,
        )
        self.control.append_audit_receipt(
            kind="authority",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "idempotent": False,
            "envelope": envelope.to_dict(),
            "control_grant": control_result,
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def activate_verified(
        self,
        *,
        request: ReflexActivationRequest,
        grant_id: str,
        evaluation_epoch: int,
        lease_until_epoch: int | None = None,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._assert_control_sha(expected_control_sha256, epoch)
        envelope = self._require_signed_grant(grant_id)
        self._verify_signed_grant(envelope, evaluation_epoch=epoch)
        revocation = self._effective_revocation(
            envelope.grant.grant_sha256,
            evaluation_epoch=epoch,
        )
        if revocation is not None:
            raise ReflexAuthorityContractError(
                "activation grant has an effective authenticated revocation"
            )
        result = self.control.activate(
            request=request,
            grant_id=grant_id,
            evaluation_epoch=epoch,
            lease_until_epoch=lease_until_epoch,
        )
        result["authenticated_grant"] = {
            "issuer_id": envelope.issuer_id,
            "key_id": envelope.key_id,
            "grant_sha256": envelope.grant.grant_sha256,
            "envelope_sha256": envelope.envelope_sha256,
        }
        return result

    @runtime_locked
    def ingest_revocation(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._assert_control_sha(expected_control_sha256, epoch)
        revocation = grant_revocation_from_payload(payload)
        self._verify_revocation(revocation)
        signed_grant = self._find_signed_grant_by_sha(
            revocation.target_grant_sha256
        )
        if signed_grant is None:
            raise ReflexAuthorityContractError(
                "revocation targets an unknown authenticated grant"
            )
        if signed_grant.issuer_id != revocation.issuer_id:
            raise ReflexAuthorityContractError(
                "revocation issuer does not match grant issuer"
            )

        path = self.revocations_dir / f"{_safe_id(revocation.revocation_id)}.json"
        if path.exists():
            existing = grant_revocation_from_payload(_read_object(path))
            if existing.envelope_sha256 != revocation.envelope_sha256:
                raise ReflexAuthorityContractError(
                    "revocation_id already exists with different contents"
                )
        else:
            _atomic_write_json(path, revocation.to_dict())

        collapse = None
        if revocation.effective_epoch <= epoch:
            collapse = self._collapse_if_target_active(
                target_grant_sha256=revocation.target_grant_sha256,
                reason="authenticated_grant_revoked",
                evaluation_epoch=epoch,
            )

        receipt = self._receipt(
            status="GRANT_REVOCATION_INGESTED",
            reason=(
                "authenticated_revocation_effective"
                if revocation.effective_epoch <= epoch
                else "authenticated_future_revocation_persisted"
            ),
            evaluation_epoch=epoch,
            issuer_id=revocation.issuer_id,
            key_id=revocation.key_id,
            grant_sha256=revocation.target_grant_sha256,
            related_sha=revocation.envelope_sha256,
            authenticated=True,
            trust_boundary_expanded=False,
        )
        self.control.append_audit_receipt(
            kind="revocation",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "revocation": revocation.to_dict(),
            "collapse": collapse,
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def evaluate_active(
        self,
        *,
        reflex_input: ReflexInput,
        baseline_provider: ReflexProvider,
        influence_provider: ReflexProvider,
        evaluation_epoch: int,
    ) -> tuple[ReflexRoutingInfluenceSignal | None, dict[str, Any]]:
        epoch = _epoch(evaluation_epoch)
        enforcement = self._enforce_active_authority(epoch)
        if enforcement is not None:
            return None, enforcement
        return self.control.evaluate_active(
            reflex_input=reflex_input,
            baseline_provider=baseline_provider,
            influence_provider=influence_provider,
            evaluation_epoch=epoch,
        )

    @runtime_locked
    def deactivate(
        self,
        *,
        reason: str,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        return self.control.deactivate(
            reason=reason,
            evaluation_epoch=_epoch(evaluation_epoch),
        )

    def _enforce_active_authority(
        self,
        evaluation_epoch: int,
    ) -> dict[str, Any] | None:
        control_status = self.control.status(
            evaluation_epoch=evaluation_epoch
        )
        activation_obj = control_status.get("activation")
        if (
            not isinstance(activation_obj, dict)
            or activation_obj.get("routing_influence_active") is not True
        ):
            return None
        grant_sha = str(activation_obj.get("activated_by_grant_sha256", ""))
        envelope = self._find_signed_grant_by_sha(grant_sha)
        if envelope is None:
            return self.control.deactivate(
                reason="active_grant_lacks_authenticated_envelope",
                evaluation_epoch=evaluation_epoch,
            )
        try:
            self._verify_signed_grant(
                envelope,
                evaluation_epoch=evaluation_epoch,
            )
        except ReflexAuthorityContractError:
            return self.control.deactivate(
                reason="active_authenticated_grant_invalid_or_expired",
                evaluation_epoch=evaluation_epoch,
            )
        if self._effective_revocation(
            grant_sha,
            evaluation_epoch=evaluation_epoch,
        ) is not None:
            return self.control.deactivate(
                reason="active_authenticated_grant_revoked",
                evaluation_epoch=evaluation_epoch,
            )
        return None

    def _collapse_if_target_active(
        self,
        *,
        target_grant_sha256: str,
        reason: str,
        evaluation_epoch: int,
    ) -> dict[str, Any] | None:
        status = self.control.status(evaluation_epoch=evaluation_epoch)
        activation = status.get("activation")
        if (
            isinstance(activation, dict)
            and activation.get("routing_influence_active") is True
            and activation.get("activated_by_grant_sha256")
            == target_grant_sha256
        ):
            return self.control.deactivate(
                reason=reason,
                evaluation_epoch=evaluation_epoch,
            )
        return None

    def _verify_signed_grant(
        self,
        envelope: SignedActivationGrantEnvelope,
        *,
        evaluation_epoch: int,
    ) -> None:
        _validate_signed_grant_shape(envelope)
        self.control.runtime.validate_activation_grant(envelope.grant)
        anchor = self._require_anchor(envelope.issuer_id, envelope.key_id)
        if PURPOSE_ACTIVATION_GRANT not in anchor.allowed_purposes:
            raise ReflexAuthorityContractError(
                "trusted key is not allowed to sign activation grants"
            )
        if envelope.grant.authority_source != envelope.issuer_id:
            raise ReflexAuthorityContractError(
                "grant authority_source must equal authenticated issuer_id"
            )
        epoch = _epoch(evaluation_epoch)
        if epoch < envelope.valid_from_epoch:
            raise ReflexAuthorityContractError(
                "authenticated grant is not valid yet"
            )
        if (
            envelope.valid_until_epoch is not None
            and epoch >= envelope.valid_until_epoch
        ):
            raise ReflexAuthorityContractError(
                "authenticated grant has expired"
            )
        _verify_ed25519(
            anchor.public_key_b64,
            canonical_authority_bytes(envelope.signing_payload()),
            envelope.signature_b64,
        )

    def _verify_revocation(self, revocation: ReflexGrantRevocation) -> None:
        _validate_revocation_shape(revocation)
        anchor = self._require_anchor(
            revocation.issuer_id,
            revocation.key_id,
        )
        if PURPOSE_GRANT_REVOCATION not in anchor.allowed_purposes:
            raise ReflexAuthorityContractError(
                "trusted key is not allowed to sign grant revocations"
            )
        _verify_ed25519(
            anchor.public_key_b64,
            canonical_authority_bytes(revocation.signing_payload()),
            revocation.signature_b64,
        )

    def _effective_revocation(
        self,
        grant_sha256: str,
        *,
        evaluation_epoch: int,
    ) -> ReflexGrantRevocation | None:
        for revocation in self._list_revocations():
            if (
                revocation.target_grant_sha256 == grant_sha256
                and revocation.effective_epoch <= evaluation_epoch
            ):
                self._verify_revocation(revocation)
                return revocation
        return None

    def _require_anchor(
        self,
        issuer_id: str,
        key_id: str,
    ) -> ReflexAuthorityTrustAnchor:
        path = self._anchor_path(issuer_id, key_id)
        if not path.exists():
            raise ReflexAuthorityContractError(
                "authority issuer/key is not locally trusted"
            )
        anchor = trust_anchor_from_payload(_read_object(path))
        _validate_trust_anchor(anchor)
        return anchor

    def _require_signed_grant(
        self,
        grant_id: str,
    ) -> SignedActivationGrantEnvelope:
        path = self.signed_grants_dir / f"{_safe_id(grant_id)}.json"
        if not path.exists():
            raise ReflexAuthorityContractError(
                "activation grant is not present as an authenticated envelope"
            )
        return signed_activation_grant_from_payload(_read_object(path))

    def _find_signed_grant_by_sha(
        self,
        grant_sha256: str,
    ) -> SignedActivationGrantEnvelope | None:
        if not self.signed_grants_dir.exists():
            return None
        for path in sorted(self.signed_grants_dir.glob("*.json")):
            envelope = signed_activation_grant_from_payload(_read_object(path))
            if envelope.grant.grant_sha256 == grant_sha256:
                return envelope
        return None

    def _list_anchors(self) -> list[ReflexAuthorityTrustAnchor]:
        if not self.trust_dir.exists():
            return []
        result = []
        for path in sorted(self.trust_dir.glob("*.json")):
            anchor = trust_anchor_from_payload(_read_object(path))
            _validate_trust_anchor(anchor)
            result.append(anchor)
        return result

    def _list_signed_grants(self) -> list[SignedActivationGrantEnvelope]:
        if not self.signed_grants_dir.exists():
            return []
        result: list[SignedActivationGrantEnvelope] = []
        for path in sorted(self.signed_grants_dir.glob("*.json")):
            envelope = signed_activation_grant_from_payload(_read_object(path))
            _validate_signed_grant_shape(envelope)
            result.append(envelope)
        return result

    def _list_revocations(self) -> list[ReflexGrantRevocation]:
        if not self.revocations_dir.exists():
            return []
        result: list[ReflexGrantRevocation] = []
        for path in sorted(self.revocations_dir.glob("*.json")):
            revocation = grant_revocation_from_payload(_read_object(path))
            _validate_revocation_shape(revocation)
            result.append(revocation)
        return result

    def _anchor_path(self, issuer_id: str, key_id: str) -> Path:
        return self.trust_dir / (
            f"{_safe_id(issuer_id)}__{_safe_id(key_id)}.json"
        )

    def _assert_control_sha(
        self,
        expected: str | None,
        evaluation_epoch: int,
    ) -> None:
        if expected is None:
            return
        _require_sha256(expected, "expected_control_sha256")
        current = self.status(evaluation_epoch=evaluation_epoch)[
            "control_sha256"
        ]
        if current != expected:
            raise ReflexAuthorityContractError(
                "control-plane compare-and-swap precondition failed"
            )

    def _control_sha(
        self,
        control_status: Mapping[str, Any],
        *,
        anchors: list[ReflexAuthorityTrustAnchor],
        grants: list[SignedActivationGrantEnvelope],
        revocations: list[ReflexGrantRevocation],
    ) -> str:
        policy = control_status.get("policy")
        activation = control_status.get("activation")
        lease = control_status.get("lease")
        ledger = self.control.ledger()
        payload = {
            "schema": "phios.reflex_authority_control_fingerprint.v0.8",
            "policy_state_sha256": (
                policy.get("state_sha256")
                if isinstance(policy, dict)
                else None
            ),
            "activation_state_sha256": (
                activation.get("state_sha256")
                if isinstance(activation, dict)
                else None
            ),
            "lease_sha256": (
                lease.get("lease_sha256")
                if isinstance(lease, dict)
                else None
            ),
            "ledger_head_sha256": (
                ledger[-1].get("entry_sha256") if ledger else None
            ),
            "trust_anchor_sha256s": sorted(
                item.anchor_sha256 for item in anchors
            ),
            "signed_grant_envelope_sha256s": sorted(
                item.envelope_sha256 for item in grants
            ),
            "revocation_envelope_sha256s": sorted(
                item.envelope_sha256 for item in revocations
            ),
        }
        return _digest(payload)

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        evaluation_epoch: int,
        issuer_id: str | None,
        key_id: str | None,
        grant_sha256: str | None,
        related_sha: str | None,
        authenticated: bool,
        trust_boundary_expanded: bool,
    ) -> ReflexAuthorityReceipt:
        payload: dict[str, object] = {
            "schema": "phios.reflex_authority_receipt.v0.8",
            "status": status,
            "reason": reason,
            "evaluation_epoch": evaluation_epoch,
            "issuer_id": issuer_id,
            "key_id": key_id,
            "grant_sha256": grant_sha256,
            "related_sha256": related_sha,
            "authenticated": authenticated,
            "trust_boundary_expanded": trust_boundary_expanded,
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexAuthorityReceipt(
            schema="phios.reflex_authority_receipt.v0.8",
            status=status,
            reason=reason,
            evaluation_epoch=evaluation_epoch,
            issuer_id=issuer_id,
            key_id=key_id,
            grant_sha256=grant_sha256,
            related_sha256=related_sha,
            authenticated=authenticated,
            trust_boundary_expanded=trust_boundary_expanded,
            routing_influence_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )


def activation_grant_signature_payload(
    *,
    issuer_id: str,
    key_id: str,
    issued_at_epoch: int,
    valid_from_epoch: int,
    valid_until_epoch: int | None,
    grant: ReflexActivationGrant,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_signed_activation_grant.v0.8",
        "issuer_id": issuer_id,
        "key_id": key_id,
        "issued_at_epoch": issued_at_epoch,
        "valid_from_epoch": valid_from_epoch,
        "valid_until_epoch": valid_until_epoch,
        "grant": grant.to_payload(),
    }


def grant_revocation_signature_payload(
    *,
    revocation_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    effective_epoch: int,
    reason: str,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_grant_revocation.v0.8",
        "revocation_id": revocation_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "target_grant_sha256": target_grant_sha256,
        "effective_epoch": effective_epoch,
        "reason": reason,
    }


def canonical_authority_bytes(payload: object) -> bytes:
    return _canonical_json(payload).encode("utf-8")


def trust_anchor_from_payload(
    payload: Mapping[str, Any],
) -> ReflexAuthorityTrustAnchor:
    if payload.get("schema") != "phios.reflex_authority_trust_anchor.v0.8":
        raise ReflexAuthorityContractError(
            "unsupported authority trust-anchor schema"
        )
    return ReflexAuthorityTrustAnchor(
        schema=str(payload["schema"]),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        algorithm=str(payload.get("algorithm", "")),
        public_key_b64=str(payload.get("public_key_b64", "")),
        allowed_purposes=_string_tuple(
            payload.get("allowed_purposes"),
            "allowed_purposes",
        ),
        anchor_sha256=str(payload.get("anchor_sha256", "")),
    )


def signed_activation_grant_from_payload(
    payload: Mapping[str, Any],
) -> SignedActivationGrantEnvelope:
    if payload.get("schema") != "phios.reflex_signed_activation_grant.v0.8":
        raise ReflexAuthorityContractError(
            "unsupported signed activation-grant schema"
        )
    grant_obj = payload.get("grant")
    if not isinstance(grant_obj, dict):
        raise ReflexAuthorityContractError("signed grant must contain grant object")
    return SignedActivationGrantEnvelope(
        schema=str(payload["schema"]),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        issued_at_epoch=_epoch_value(
            payload.get("issued_at_epoch"),
            "issued_at_epoch",
        ),
        valid_from_epoch=_epoch_value(
            payload.get("valid_from_epoch"),
            "valid_from_epoch",
        ),
        valid_until_epoch=_optional_epoch(
            payload.get("valid_until_epoch"),
            "valid_until_epoch",
        ),
        grant=activation_grant_from_payload(grant_obj),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def grant_revocation_from_payload(
    payload: Mapping[str, Any],
) -> ReflexGrantRevocation:
    if payload.get("schema") != "phios.reflex_grant_revocation.v0.8":
        raise ReflexAuthorityContractError(
            "unsupported grant-revocation schema"
        )
    return ReflexGrantRevocation(
        schema=str(payload["schema"]),
        revocation_id=str(payload.get("revocation_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        target_grant_sha256=str(payload.get("target_grant_sha256", "")),
        effective_epoch=_epoch_value(
            payload.get("effective_epoch"),
            "effective_epoch",
        ),
        reason=str(payload.get("reason", "")),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def build_trust_anchor(
    *,
    issuer_id: str,
    key_id: str,
    public_key_b64: str,
    allowed_purposes: tuple[str, ...] = ALLOWED_PURPOSES,
) -> ReflexAuthorityTrustAnchor:
    payload: dict[str, object] = {
        "schema": "phios.reflex_authority_trust_anchor.v0.8",
        "issuer_id": issuer_id,
        "key_id": key_id,
        "algorithm": "ed25519",
        "public_key_b64": public_key_b64,
        "allowed_purposes": list(tuple(sorted(set(allowed_purposes)))),
    }
    anchor = ReflexAuthorityTrustAnchor(
        schema=str(payload["schema"]),
        issuer_id=issuer_id,
        key_id=key_id,
        algorithm="ed25519",
        public_key_b64=public_key_b64,
        allowed_purposes=tuple(sorted(set(allowed_purposes))),
        anchor_sha256=_digest(payload),
    )
    _validate_trust_anchor(anchor)
    return anchor


def build_signed_activation_grant_envelope(
    *,
    issuer_id: str,
    key_id: str,
    issued_at_epoch: int,
    valid_from_epoch: int,
    valid_until_epoch: int | None,
    grant: ReflexActivationGrant,
    signature_b64: str,
) -> SignedActivationGrantEnvelope:
    payload = activation_grant_signature_payload(
        issuer_id=issuer_id,
        key_id=key_id,
        issued_at_epoch=issued_at_epoch,
        valid_from_epoch=valid_from_epoch,
        valid_until_epoch=valid_until_epoch,
        grant=grant,
    )
    envelope_payload = dict(payload)
    envelope_payload["signature_b64"] = signature_b64
    envelope = SignedActivationGrantEnvelope(
        schema="phios.reflex_signed_activation_grant.v0.8",
        issuer_id=issuer_id,
        key_id=key_id,
        issued_at_epoch=issued_at_epoch,
        valid_from_epoch=valid_from_epoch,
        valid_until_epoch=valid_until_epoch,
        grant=grant,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope_payload),
    )
    _validate_signed_grant_shape(envelope)
    return envelope


def build_grant_revocation(
    *,
    revocation_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    effective_epoch: int,
    reason: str,
    signature_b64: str,
) -> ReflexGrantRevocation:
    payload = grant_revocation_signature_payload(
        revocation_id=revocation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        effective_epoch=effective_epoch,
        reason=reason,
    )
    envelope_payload = dict(payload)
    envelope_payload["signature_b64"] = signature_b64
    revocation = ReflexGrantRevocation(
        schema="phios.reflex_grant_revocation.v0.8",
        revocation_id=revocation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        effective_epoch=effective_epoch,
        reason=reason,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope_payload),
    )
    _validate_revocation_shape(revocation)
    return revocation


def _validate_trust_anchor(anchor: ReflexAuthorityTrustAnchor) -> None:
    _safe_id(anchor.issuer_id)
    _safe_id(anchor.key_id)
    if anchor.algorithm != "ed25519":
        raise ReflexAuthorityContractError("only ed25519 trust anchors are supported")
    purposes = tuple(sorted(set(anchor.allowed_purposes)))
    if not purposes or purposes != anchor.allowed_purposes:
        raise ReflexAuthorityContractError(
            "allowed_purposes must be unique and canonical"
        )
    if any(purpose not in ALLOWED_PURPOSES for purpose in purposes):
        raise ReflexAuthorityContractError("unsupported authority purpose")
    raw = _decode_b64(anchor.public_key_b64, "public_key_b64")
    if len(raw) != 32:
        raise ReflexAuthorityContractError(
            "ed25519 public key must contain exactly 32 bytes"
        )
    payload = anchor.to_dict()
    digest = str(payload.pop("anchor_sha256"))
    _require_sha256(digest, "anchor_sha256")
    if _digest(payload) != digest:
        raise ReflexAuthorityContractError(
            "trust-anchor hash does not match contents"
        )


def _validate_signed_grant_shape(
    envelope: SignedActivationGrantEnvelope,
) -> None:
    _safe_id(envelope.issuer_id)
    _safe_id(envelope.key_id)
    _epoch(envelope.issued_at_epoch)
    _epoch(envelope.valid_from_epoch)
    if envelope.issued_at_epoch > envelope.valid_from_epoch:
        raise ReflexAuthorityContractError(
            "issued_at_epoch cannot be after valid_from_epoch"
        )
    if envelope.valid_until_epoch is not None:
        _epoch(envelope.valid_until_epoch)
        if envelope.valid_until_epoch <= envelope.valid_from_epoch:
            raise ReflexAuthorityContractError(
                "valid_until_epoch must be greater than valid_from_epoch"
            )
    signature = _decode_b64(envelope.signature_b64, "signature_b64")
    if len(signature) != 64:
        raise ReflexAuthorityContractError(
            "ed25519 signature must contain exactly 64 bytes"
        )
    payload = envelope.to_dict()
    digest = str(payload.pop("envelope_sha256"))
    _require_sha256(digest, "envelope_sha256")
    if _digest(payload) != digest:
        raise ReflexAuthorityContractError(
            "signed activation-grant envelope hash does not match contents"
        )


def _validate_revocation_shape(revocation: ReflexGrantRevocation) -> None:
    _safe_id(revocation.revocation_id)
    _safe_id(revocation.issuer_id)
    _safe_id(revocation.key_id)
    _require_sha256(
        revocation.target_grant_sha256,
        "target_grant_sha256",
    )
    _epoch(revocation.effective_epoch)
    if not revocation.reason.strip():
        raise ReflexAuthorityContractError(
            "revocation reason must be non-empty"
        )
    signature = _decode_b64(revocation.signature_b64, "signature_b64")
    if len(signature) != 64:
        raise ReflexAuthorityContractError(
            "ed25519 signature must contain exactly 64 bytes"
        )
    payload = revocation.to_dict()
    digest = str(payload.pop("envelope_sha256"))
    _require_sha256(digest, "envelope_sha256")
    if _digest(payload) != digest:
        raise ReflexAuthorityContractError(
            "revocation envelope hash does not match contents"
        )


def _verify_ed25519(
    public_key_b64: str,
    message: bytes,
    signature_b64: str,
) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise ReflexAuthorityContractError(
            "Ed25519 verification requires PhiOS reflex-authority extra"
        ) from exc

    public_bytes = _decode_b64(public_key_b64, "public_key_b64")
    signature = _decode_b64(signature_b64, "signature_b64")
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature,
            message,
        )
    except InvalidSignature as exc:
        raise ReflexAuthorityContractError(
            "Ed25519 authority signature verification failed"
        ) from exc
    except ValueError as exc:
        raise ReflexAuthorityContractError(
            "invalid Ed25519 public key or signature"
        ) from exc


def _atomic_write_json(path: Path, payload: object) -> None:
    # Authority writes occur while the shared v0.7 control lock is held.
    # Reuse the same durability contract without importing a private helper.
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReflexAuthorityContractError(
            f"invalid authority JSON: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise ReflexAuthorityContractError(
            f"{path.name} must contain a JSON object"
        )
    return dict(value)


def _decode_b64(value: str, label: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ReflexAuthorityContractError(
            f"{label} must be canonical base64"
        ) from exc


def _safe_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", normalized):
        raise ReflexAuthorityContractError(
            "authority identifier contains unsupported characters"
        )
    return normalized


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReflexAuthorityContractError(f"{label} must be a list")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise ReflexAuthorityContractError(
            f"{label} cannot contain empty strings"
        )
    return result


def _optional_epoch(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _epoch_value(value, label)


def _epoch_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexAuthorityContractError(
            f"{label} must be a non-negative integer"
        )
    return value


def _epoch(value: int) -> int:
    return _epoch_value(value, "evaluation_epoch")


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexAuthorityContractError(
            f"{label} must be a SHA-256 hex digest"
        )
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexAuthorityContractError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc


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
        raise ReflexAuthorityContractError(
            "authority payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
