"""PhiReflex v0.9 trust lifecycle, attestation, and bounded grant use.

v0.9 composes on top of v0.8 authenticated authority. It does not widen the
routing surface or add action/execution authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from phios.reflex.authority import (
    PURPOSE_GRANT_USE_POLICY,
    PURPOSE_LEDGER_CHECKPOINT,
    PURPOSE_LEASE_RENEWAL,
    PURPOSE_PROVIDER_MANIFEST,
    PURPOSE_TRUST_TRANSITION,
    ReflexAuthorityContractError,
    ReflexAuthorityPlane,
    ReflexAuthorityTrustAnchor,
    SignedActivationGrantEnvelope,
    trust_anchor_from_payload,
)
from phios.reflex.control_plane import ReflexRuntimeControlPlane
from phios.reflex.coordination import runtime_locked
from phios.reflex.models import ReflexInput
from phios.reflex.providers.base import ReflexProvider
from phios.reflex.runtime_influence import (
    ReflexActivationRequest,
    ReflexRoutingInfluenceSignal,
)


class ReflexLifecycleContractError(ValueError):
    """Raised when v0.9 lifecycle or attestation input is invalid."""


@dataclass(frozen=True, slots=True)
class ReflexTrustTransition:
    schema: str
    transition_id: str
    issuer_id: str
    key_id: str
    action: str
    issued_at_epoch: int
    effective_epoch: int
    reason: str
    replacement_anchor: ReflexAuthorityTrustAnchor | None
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return trust_transition_signature_payload(
            transition_id=self.transition_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            action=self.action,
            issued_at_epoch=self.issued_at_epoch,
            effective_epoch=self.effective_epoch,
            reason=self.reason,
            replacement_anchor=self.replacement_anchor,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexLedgerCheckpoint:
    schema: str
    checkpoint_id: str
    issuer_id: str
    key_id: str
    created_at_epoch: int
    ledger_entry_count: int
    ledger_head_sha256: str | None
    control_sha256: str
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return ledger_checkpoint_signature_payload(
            checkpoint_id=self.checkpoint_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            created_at_epoch=self.created_at_epoch,
            ledger_entry_count=self.ledger_entry_count,
            ledger_head_sha256=self.ledger_head_sha256,
            control_sha256=self.control_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexGrantUsePolicy:
    schema: str
    policy_id: str
    issuer_id: str
    key_id: str
    target_grant_sha256: str
    max_activations: int
    issued_at_epoch: int
    effective_epoch: int
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return grant_use_policy_signature_payload(
            policy_id=self.policy_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            target_grant_sha256=self.target_grant_sha256,
            max_activations=self.max_activations,
            issued_at_epoch=self.issued_at_epoch,
            effective_epoch=self.effective_epoch,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexProviderManifest:
    schema: str
    manifest_id: str
    issuer_id: str
    key_id: str
    provider: str
    models: tuple[str, ...]
    adapter_id: str
    adapter_version: str
    issued_at_epoch: int
    effective_epoch: int
    valid_until_epoch: int | None
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return provider_manifest_signature_payload(
            manifest_id=self.manifest_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            provider=self.provider,
            models=self.models,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            issued_at_epoch=self.issued_at_epoch,
            effective_epoch=self.effective_epoch,
            valid_until_epoch=self.valid_until_epoch,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexLeaseRenewal:
    schema: str
    renewal_id: str
    issuer_id: str
    key_id: str
    target_grant_sha256: str
    activation_state_sha256: str
    current_lease_sha256: str
    new_valid_through_epoch: int
    issued_at_epoch: int
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return lease_renewal_signature_payload(
            renewal_id=self.renewal_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            target_grant_sha256=self.target_grant_sha256,
            activation_state_sha256=self.activation_state_sha256,
            current_lease_sha256=self.current_lease_sha256,
            new_valid_through_epoch=self.new_valid_through_epoch,
            issued_at_epoch=self.issued_at_epoch,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexLifecycleReceipt:
    schema: str
    status: str
    reason: str
    evaluation_epoch: int
    issuer_id: str | None
    key_id: str | None
    related_sha256: str | None
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
            "related_sha256": self.related_sha256,
            "routing_influence_authority": self.routing_influence_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class ReflexTrustLifecyclePlane:
    """v0.9 lifecycle wrapper around the v0.8 authenticated authority plane."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        control: ReflexRuntimeControlPlane | None = None,
        authority: ReflexAuthorityPlane | None = None,
    ) -> None:
        self.control = control or ReflexRuntimeControlPlane(root=root)
        self.authority = authority or ReflexAuthorityPlane(control=self.control)
        self.root = self.control.root / "lifecycle"
        self._runtime_lock = self.control._runtime_lock

    @property
    def transitions_dir(self) -> Path:
        return self.root / "trust-transitions"

    @property
    def checkpoints_dir(self) -> Path:
        return self.root / "checkpoints"

    @property
    def use_policies_dir(self) -> Path:
        return self.root / "grant-use-policies"

    @property
    def usage_dir(self) -> Path:
        return self.root / "grant-usage"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "provider-manifests"

    @property
    def renewals_dir(self) -> Path:
        return self.root / "lease-renewals"

    @runtime_locked
    def status(
        self,
        *,
        evaluation_epoch: int,
        adapter_id: str | None = None,
        adapter_version: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._materialize_effective_rotations(epoch)
        authority_status = self.authority.status(evaluation_epoch=epoch)
        enforcement = self._enforce_live_lifecycle(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        if enforcement is not None:
            authority_status = self.authority.status(evaluation_epoch=epoch)
        return {
            "ok": True,
            "evaluation_epoch": epoch,
            "routing_influence_active": authority_status.get(
                "routing_influence_active", False
            ),
            "lifecycle_enforcement": enforcement,
            "authority": authority_status,
            "trust_transitions": [
                item.to_dict() for item in self._list_transitions()
            ],
            "checkpoints": [
                item.to_dict() for item in self._list_checkpoints()
            ],
            "grant_use_policies": [
                item.to_dict() for item in self._list_use_policies()
            ],
            "grant_usage": self._all_usage(),
            "provider_manifests": [
                item.to_dict() for item in self._list_manifests()
            ],
            "lease_renewals": [
                item.to_dict() for item in self._list_renewals()
            ],
        }

    @runtime_locked
    def ingest_trust_transition(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        transition = trust_transition_from_payload(payload)
        _validate_trust_transition_shape(transition)
        if transition.issued_at_epoch > epoch:
            raise ReflexLifecycleContractError(
                "trust transition cannot be ingested before issued_at_epoch"
            )
        if not self._key_is_live(
            transition.issuer_id,
            transition.key_id,
            epoch,
        ):
            raise ReflexLifecycleContractError(
                "trust transition signer is not live at ingestion epoch"
            )
        self.authority.verify_signed_payload(
            issuer_id=transition.issuer_id,
            key_id=transition.key_id,
            purpose=PURPOSE_TRUST_TRANSITION,
            payload=transition.signing_payload(),
            signature_b64=transition.signature_b64,
        )
        path = self.transitions_dir / f"{_safe_id(transition.transition_id)}.json"
        _idempotent_write(path, transition.to_dict(), transition.envelope_sha256)

        if transition.effective_epoch <= epoch:
            self._materialize_effective_rotations(epoch)
            self._collapse_if_key_retired(
                issuer_id=transition.issuer_id,
                key_id=transition.key_id,
                evaluation_epoch=epoch,
            )
        receipt = self._receipt(
            status="TRUST_TRANSITION_INGESTED",
            reason=(
                "effective_trust_transition"
                if transition.effective_epoch <= epoch
                else "future_trust_transition_persisted"
            ),
            evaluation_epoch=epoch,
            issuer_id=transition.issuer_id,
            key_id=transition.key_id,
            related_sha=transition.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="lifecycle",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "transition": transition.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def ingest_grant_use_policy(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        policy = grant_use_policy_from_payload(payload)
        _validate_grant_use_policy_shape(policy)
        envelope = self._require_grant(policy.target_grant_sha256)
        self._require_same_issuer(envelope, policy.issuer_id)
        self._require_live_signer(policy.issuer_id, policy.key_id, epoch)
        self.authority.verify_signed_payload(
            issuer_id=policy.issuer_id,
            key_id=policy.key_id,
            purpose=PURPOSE_GRANT_USE_POLICY,
            payload=policy.signing_payload(),
            signature_b64=policy.signature_b64,
        )
        path = self.use_policies_dir / f"{policy.target_grant_sha256}.json"
        if path.exists():
            existing = grant_use_policy_from_payload(_read_object(path))
            _validate_grant_use_policy_shape(existing)
            if policy.max_activations > existing.max_activations:
                raise ReflexLifecycleContractError(
                    "grant-use policy may reduce but not increase max_activations"
                )
            if existing.envelope_sha256 == policy.envelope_sha256:
                return {"ok": True, "idempotent": True, "policy": existing.to_dict()}
        _atomic_write_json(path, policy.to_dict())
        receipt = self._receipt(
            status="GRANT_USE_POLICY_INGESTED",
            reason="signed_activation_count_limit_persisted",
            evaluation_epoch=epoch,
            issuer_id=policy.issuer_id,
            key_id=policy.key_id,
            related_sha=policy.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="usage",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {"ok": True, "idempotent": False, "policy": policy.to_dict()}

    @runtime_locked
    def ingest_provider_manifest(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        manifest = provider_manifest_from_payload(payload)
        _validate_provider_manifest_shape(manifest)
        self._require_live_signer(manifest.issuer_id, manifest.key_id, epoch)
        self.authority.verify_signed_payload(
            issuer_id=manifest.issuer_id,
            key_id=manifest.key_id,
            purpose=PURPOSE_PROVIDER_MANIFEST,
            payload=manifest.signing_payload(),
            signature_b64=manifest.signature_b64,
        )
        path = self.manifests_dir / f"{_safe_id(manifest.manifest_id)}.json"
        _idempotent_write(path, manifest.to_dict(), manifest.envelope_sha256)
        receipt = self._receipt(
            status="PROVIDER_MANIFEST_INGESTED",
            reason="authenticated_runtime_adapter_manifest_persisted",
            evaluation_epoch=epoch,
            issuer_id=manifest.issuer_id,
            key_id=manifest.key_id,
            related_sha=manifest.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="manifest",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {"ok": True, "manifest": manifest.to_dict(), "receipt": receipt.to_dict()}

    @runtime_locked
    def activate_verified(
        self,
        *,
        request: ReflexActivationRequest,
        grant_id: str,
        adapter_id: str,
        adapter_version: str,
        evaluation_epoch: int,
        lease_until_epoch: int | None = None,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._materialize_effective_rotations(epoch)
        envelope = self._require_grant_by_id(grant_id)
        self._require_live_signer(envelope.issuer_id, envelope.key_id, epoch)
        self._require_provider_manifest(
            envelope=envelope,
            provider=request.provider,
            models=request.models,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            evaluation_epoch=epoch,
        )
        use_policy = self._require_use_policy(
            envelope.grant.grant_sha256,
            evaluation_epoch=epoch,
        )
        usage = self._usage(envelope.grant.grant_sha256)
        if usage >= use_policy.max_activations:
            raise ReflexLifecycleContractError(
                "authenticated activation grant use limit exhausted"
            )

        result = self.authority.activate_verified(
            request=request,
            grant_id=grant_id,
            evaluation_epoch=epoch,
            lease_until_epoch=lease_until_epoch,
            expected_control_sha256=expected_control_sha256,
        )
        if result.get("ok") is True:
            self._set_usage(
                envelope.grant.grant_sha256,
                usage + 1,
                evaluation_epoch=epoch,
                activation_state_sha256=_activation_sha(result),
            )
        result["grant_use"] = {
            "used": usage + (1 if result.get("ok") is True else 0),
            "max_activations": use_policy.max_activations,
            "remaining": max(
                0,
                use_policy.max_activations
                - usage
                - (1 if result.get("ok") is True else 0),
            ),
        }
        return result

    @runtime_locked
    def renew_lease(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        renewal = lease_renewal_from_payload(payload)
        _validate_lease_renewal_shape(renewal)
        envelope = self._require_grant(renewal.target_grant_sha256)
        self._require_same_issuer(envelope, renewal.issuer_id)
        self._require_live_signer(renewal.issuer_id, renewal.key_id, epoch)
        self.authority.verify_signed_payload(
            issuer_id=renewal.issuer_id,
            key_id=renewal.key_id,
            purpose=PURPOSE_LEASE_RENEWAL,
            payload=renewal.signing_payload(),
            signature_b64=renewal.signature_b64,
        )
        authority_status = self.authority.status(evaluation_epoch=epoch)
        control = authority_status.get("control")
        if not isinstance(control, dict):
            raise ReflexLifecycleContractError("authority status omitted control state")
        activation = control.get("activation")
        lease = control.get("lease")
        if not isinstance(activation, dict) or not isinstance(lease, dict):
            raise ReflexLifecycleContractError(
                "lease renewal requires active persisted activation and lease"
            )
        if activation.get("state_sha256") != renewal.activation_state_sha256:
            raise ReflexLifecycleContractError(
                "lease renewal activation scope mismatch"
            )
        if lease.get("lease_sha256") != renewal.current_lease_sha256:
            raise ReflexLifecycleContractError(
                "lease renewal current-lease scope mismatch"
            )
        if activation.get("activated_by_grant_sha256") != renewal.target_grant_sha256:
            raise ReflexLifecycleContractError(
                "lease renewal grant scope mismatch"
            )
        path = self.renewals_dir / f"{_safe_id(renewal.renewal_id)}.json"
        _idempotent_write(path, renewal.to_dict(), renewal.envelope_sha256)
        result = self.control.renew_lease_authorized(
            valid_through_epoch=renewal.new_valid_through_epoch,
            evaluation_epoch=epoch,
            authorization_sha256=renewal.envelope_sha256,
        )
        receipt = self._receipt(
            status="LEASE_RENEWAL_APPLIED",
            reason="authenticated_grant_bound_lease_extension",
            evaluation_epoch=epoch,
            issuer_id=renewal.issuer_id,
            key_id=renewal.key_id,
            related_sha=renewal.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="lease",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "renewal": renewal.to_dict(),
            "control": result,
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def ingest_checkpoint(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        checkpoint = ledger_checkpoint_from_payload(payload)
        _validate_checkpoint_shape(checkpoint)
        self._require_live_signer(checkpoint.issuer_id, checkpoint.key_id, epoch)
        self.authority.verify_signed_payload(
            issuer_id=checkpoint.issuer_id,
            key_id=checkpoint.key_id,
            purpose=PURPOSE_LEDGER_CHECKPOINT,
            payload=checkpoint.signing_payload(),
            signature_b64=checkpoint.signature_b64,
        )
        status = self.authority.status(evaluation_epoch=epoch)
        ledger = self.control.ledger()
        head = ledger[-1]["entry_sha256"] if ledger else None
        if checkpoint.ledger_entry_count != len(ledger):
            raise ReflexLifecycleContractError(
                "checkpoint ledger-entry count does not match current ledger"
            )
        if checkpoint.ledger_head_sha256 != head:
            raise ReflexLifecycleContractError(
                "checkpoint ledger head does not match current ledger"
            )
        if checkpoint.control_sha256 != status["control_sha256"]:
            raise ReflexLifecycleContractError(
                "checkpoint control fingerprint does not match current state"
            )
        path = self.checkpoints_dir / f"{_safe_id(checkpoint.checkpoint_id)}.json"
        _idempotent_write(path, checkpoint.to_dict(), checkpoint.envelope_sha256)
        receipt = self._receipt(
            status="LEDGER_CHECKPOINT_INGESTED",
            reason="signed_runtime_ledger_checkpoint_verified",
            evaluation_epoch=epoch,
            issuer_id=checkpoint.issuer_id,
            key_id=checkpoint.key_id,
            related_sha=checkpoint.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="attestation",
            evaluation_epoch=epoch,
            receipt=receipt.to_dict(),
        )
        return {
            "ok": True,
            "checkpoint": checkpoint.to_dict(),
            "receipt": receipt.to_dict(),
        }

    @runtime_locked
    def evaluate_active(
        self,
        *,
        reflex_input: ReflexInput,
        baseline_provider: ReflexProvider,
        influence_provider: ReflexProvider,
        adapter_id: str,
        adapter_version: str,
        evaluation_epoch: int,
    ) -> tuple[ReflexRoutingInfluenceSignal | None, dict[str, Any]]:
        epoch = _epoch(evaluation_epoch)
        enforcement = self._enforce_live_lifecycle(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        if enforcement is not None:
            return None, enforcement
        return self.authority.evaluate_active(
            reflex_input=reflex_input,
            baseline_provider=baseline_provider,
            influence_provider=influence_provider,
            evaluation_epoch=epoch,
        )

    def _enforce_live_lifecycle(
        self,
        *,
        evaluation_epoch: int,
        adapter_id: str | None,
        adapter_version: str | None,
    ) -> dict[str, Any] | None:
        self._materialize_effective_rotations(evaluation_epoch)
        status = self.authority.status(evaluation_epoch=evaluation_epoch)
        control = status.get("control")
        activation = control.get("activation") if isinstance(control, dict) else None
        if not isinstance(activation, dict) or activation.get(
            "routing_influence_active"
        ) is not True:
            return None
        grant_sha = str(activation.get("activated_by_grant_sha256", ""))
        envelope = self._require_grant(grant_sha)
        if not self._key_is_live(envelope.issuer_id, envelope.key_id, evaluation_epoch):
            return self.authority.deactivate(
                reason="authenticated_signing_key_retired",
                evaluation_epoch=evaluation_epoch,
            )
        if adapter_id is not None and adapter_version is not None:
            models_obj = activation.get("models")
            models = tuple(str(item) for item in models_obj) if isinstance(
                models_obj, list
            ) else ()
            try:
                self._require_provider_manifest(
                    envelope=envelope,
                    provider=str(activation.get("provider", "")),
                    models=models,
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                    evaluation_epoch=evaluation_epoch,
                )
            except ReflexLifecycleContractError:
                return self.authority.deactivate(
                    reason="authenticated_provider_manifest_missing_or_invalid",
                    evaluation_epoch=evaluation_epoch,
                )
        return None

    def _materialize_effective_rotations(self, evaluation_epoch: int) -> None:
        for transition in self._list_transitions():
            if transition.effective_epoch > evaluation_epoch:
                continue
            self._verify_transition_signature(transition)
            if transition.action != "ROTATE" or transition.replacement_anchor is None:
                continue
            replacement = transition.replacement_anchor
            try:
                existing = self.authority.require_trust_anchor(
                    issuer_id=replacement.issuer_id,
                    key_id=replacement.key_id,
                )
            except ReflexAuthorityContractError:
                self.authority.ingest_trust_anchor(
                    replacement.to_dict(),
                    evaluation_epoch=evaluation_epoch,
                )
            else:
                if existing.anchor_sha256 != replacement.anchor_sha256:
                    raise ReflexLifecycleContractError(
                        "materialized replacement trust anchor conflicts"
                    )

    def _key_is_live(self, issuer_id: str, key_id: str, evaluation_epoch: int) -> bool:
        try:
            self.authority.require_trust_anchor(
                issuer_id=issuer_id,
                key_id=key_id,
            )
        except ReflexAuthorityContractError:
            return False
        for transition in self._list_transitions():
            if (
                transition.issuer_id == issuer_id
                and transition.key_id == key_id
                and transition.effective_epoch <= evaluation_epoch
            ):
                self._verify_transition_signature(transition)
                return False
        return True

    def _verify_transition_signature(self, transition: ReflexTrustTransition) -> None:
        self.authority.verify_signed_payload(
            issuer_id=transition.issuer_id,
            key_id=transition.key_id,
            purpose=PURPOSE_TRUST_TRANSITION,
            payload=transition.signing_payload(),
            signature_b64=transition.signature_b64,
        )

    def _require_live_signer(self, issuer_id: str, key_id: str, epoch: int) -> None:
        if not self._key_is_live(issuer_id, key_id, epoch):
            raise ReflexLifecycleContractError(
                "authority signer key is retired, disabled, or untrusted"
            )

    def _collapse_if_key_retired(
        self,
        *,
        issuer_id: str,
        key_id: str,
        evaluation_epoch: int,
    ) -> None:
        status = self.authority.status(evaluation_epoch=evaluation_epoch)
        control = status.get("control")
        activation = control.get("activation") if isinstance(control, dict) else None
        if not isinstance(activation, dict) or activation.get(
            "routing_influence_active"
        ) is not True:
            return
        grant_sha = str(activation.get("activated_by_grant_sha256", ""))
        envelope = self._require_grant(grant_sha)
        if envelope.issuer_id == issuer_id and envelope.key_id == key_id:
            self.authority.deactivate(
                reason="authenticated_signing_key_retired",
                evaluation_epoch=evaluation_epoch,
            )

    def _require_provider_manifest(
        self,
        *,
        envelope: SignedActivationGrantEnvelope,
        provider: str,
        models: tuple[str, ...],
        adapter_id: str,
        adapter_version: str,
        evaluation_epoch: int,
    ) -> ReflexProviderManifest:
        for manifest in self._list_manifests():
            if manifest.issuer_id != envelope.issuer_id:
                continue
            if manifest.provider != provider:
                continue
            if not set(models).issubset(set(manifest.models)):
                continue
            if manifest.adapter_id != adapter_id or manifest.adapter_version != adapter_version:
                continue
            if manifest.effective_epoch > evaluation_epoch:
                continue
            if (
                manifest.valid_until_epoch is not None
                and evaluation_epoch >= manifest.valid_until_epoch
            ):
                continue
            if not self._key_is_live(
                manifest.issuer_id,
                manifest.key_id,
                evaluation_epoch,
            ):
                continue
            self.authority.verify_signed_payload(
                issuer_id=manifest.issuer_id,
                key_id=manifest.key_id,
                purpose=PURPOSE_PROVIDER_MANIFEST,
                payload=manifest.signing_payload(),
                signature_b64=manifest.signature_b64,
            )
            return manifest
        raise ReflexLifecycleContractError(
            "no effective authenticated provider manifest matches runtime adapter"
        )

    def _require_use_policy(
        self,
        grant_sha256: str,
        *,
        evaluation_epoch: int,
    ) -> ReflexGrantUsePolicy:
        path = self.use_policies_dir / f"{grant_sha256}.json"
        if not path.exists():
            raise ReflexLifecycleContractError(
                "v0.9 activation requires an authenticated grant-use policy"
            )
        policy = grant_use_policy_from_payload(_read_object(path))
        _validate_grant_use_policy_shape(policy)
        if policy.effective_epoch > evaluation_epoch:
            raise ReflexLifecycleContractError(
                "grant-use policy is not effective yet"
            )
        self._require_live_signer(policy.issuer_id, policy.key_id, evaluation_epoch)
        self.authority.verify_signed_payload(
            issuer_id=policy.issuer_id,
            key_id=policy.key_id,
            purpose=PURPOSE_GRANT_USE_POLICY,
            payload=policy.signing_payload(),
            signature_b64=policy.signature_b64,
        )
        return policy

    def _usage(self, grant_sha256: str) -> int:
        path = self.usage_dir / f"{grant_sha256}.json"
        if not path.exists():
            return 0
        payload = _read_object(path)
        if payload.get("schema") != "phios.reflex_grant_usage.v0.9":
            raise ReflexLifecycleContractError("unsupported grant-usage schema")
        if payload.get("grant_sha256") != grant_sha256:
            raise ReflexLifecycleContractError("grant-usage scope mismatch")
        count = payload.get("activation_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ReflexLifecycleContractError("invalid activation_count")
        expected = dict(payload)
        digest = str(expected.pop("usage_sha256", ""))
        if _digest(expected) != digest:
            raise ReflexLifecycleContractError("grant-usage hash mismatch")
        return count

    def _set_usage(
        self,
        grant_sha256: str,
        count: int,
        *,
        evaluation_epoch: int,
        activation_state_sha256: str,
    ) -> None:
        payload: dict[str, object] = {
            "schema": "phios.reflex_grant_usage.v0.9",
            "grant_sha256": grant_sha256,
            "activation_count": count,
            "last_evaluation_epoch": evaluation_epoch,
            "last_activation_state_sha256": activation_state_sha256,
        }
        payload["usage_sha256"] = _digest(payload)
        _atomic_write_json(
            self.usage_dir / f"{grant_sha256}.json",
            payload,
        )
        receipt = self._receipt(
            status="GRANT_USE_CONSUMED",
            reason="successful_authenticated_activation_counted",
            evaluation_epoch=evaluation_epoch,
            issuer_id=None,
            key_id=None,
            related_sha=str(payload["usage_sha256"]),
        )
        self.control.append_audit_receipt(
            kind="usage",
            evaluation_epoch=evaluation_epoch,
            receipt=receipt.to_dict(),
        )

    def _all_usage(self) -> list[dict[str, Any]]:
        if not self.usage_dir.exists():
            return []
        return [_read_object(path) for path in sorted(self.usage_dir.glob("*.json"))]

    def _require_grant(self, grant_sha256: str) -> SignedActivationGrantEnvelope:
        envelope = self.authority.find_signed_grant_by_sha256(grant_sha256)
        if envelope is None:
            raise ReflexLifecycleContractError(
                "authenticated grant envelope not found"
            )
        return envelope

    def _require_grant_by_id(self, grant_id: str) -> SignedActivationGrantEnvelope:
        envelope = self.authority.find_signed_grant_by_id(grant_id)
        if envelope is None:
            raise ReflexLifecycleContractError("authenticated grant_id not found")
        return envelope

    @staticmethod
    def _require_same_issuer(
        envelope: SignedActivationGrantEnvelope,
        issuer_id: str,
    ) -> None:
        if envelope.issuer_id != issuer_id:
            raise ReflexLifecycleContractError(
                "signed policy issuer does not match activation-grant issuer"
            )

    def _list_transitions(self) -> list[ReflexTrustTransition]:
        return _read_typed_dir(
            self.transitions_dir,
            trust_transition_from_payload,
            _validate_trust_transition_shape,
        )

    def _list_checkpoints(self) -> list[ReflexLedgerCheckpoint]:
        return _read_typed_dir(
            self.checkpoints_dir,
            ledger_checkpoint_from_payload,
            _validate_checkpoint_shape,
        )

    def _list_use_policies(self) -> list[ReflexGrantUsePolicy]:
        return _read_typed_dir(
            self.use_policies_dir,
            grant_use_policy_from_payload,
            _validate_grant_use_policy_shape,
        )

    def _list_manifests(self) -> list[ReflexProviderManifest]:
        return _read_typed_dir(
            self.manifests_dir,
            provider_manifest_from_payload,
            _validate_provider_manifest_shape,
        )

    def _list_renewals(self) -> list[ReflexLeaseRenewal]:
        return _read_typed_dir(
            self.renewals_dir,
            lease_renewal_from_payload,
            _validate_lease_renewal_shape,
        )

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        evaluation_epoch: int,
        issuer_id: str | None,
        key_id: str | None,
        related_sha: str | None,
    ) -> ReflexLifecycleReceipt:
        payload: dict[str, object] = {
            "schema": "phios.reflex_lifecycle_receipt.v0.9",
            "status": status,
            "reason": reason,
            "evaluation_epoch": evaluation_epoch,
            "issuer_id": issuer_id,
            "key_id": key_id,
            "related_sha256": related_sha,
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexLifecycleReceipt(
            schema="phios.reflex_lifecycle_receipt.v0.9",
            status=status,
            reason=reason,
            evaluation_epoch=evaluation_epoch,
            issuer_id=issuer_id,
            key_id=key_id,
            related_sha256=related_sha,
            routing_influence_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )


def trust_transition_signature_payload(
    *,
    transition_id: str,
    issuer_id: str,
    key_id: str,
    action: str,
    issued_at_epoch: int,
    effective_epoch: int,
    reason: str,
    replacement_anchor: ReflexAuthorityTrustAnchor | None,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_trust_transition.v0.9",
        "transition_id": transition_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "action": action,
        "issued_at_epoch": issued_at_epoch,
        "effective_epoch": effective_epoch,
        "reason": reason,
        "replacement_anchor": (
            replacement_anchor.to_dict()
            if replacement_anchor is not None
            else None
        ),
    }


def ledger_checkpoint_signature_payload(
    *,
    checkpoint_id: str,
    issuer_id: str,
    key_id: str,
    created_at_epoch: int,
    ledger_entry_count: int,
    ledger_head_sha256: str | None,
    control_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_ledger_checkpoint.v0.9",
        "checkpoint_id": checkpoint_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "created_at_epoch": created_at_epoch,
        "ledger_entry_count": ledger_entry_count,
        "ledger_head_sha256": ledger_head_sha256,
        "control_sha256": control_sha256,
    }


def grant_use_policy_signature_payload(
    *,
    policy_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    max_activations: int,
    issued_at_epoch: int,
    effective_epoch: int,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_grant_use_policy.v0.9",
        "policy_id": policy_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "target_grant_sha256": target_grant_sha256,
        "max_activations": max_activations,
        "issued_at_epoch": issued_at_epoch,
        "effective_epoch": effective_epoch,
    }


def provider_manifest_signature_payload(
    *,
    manifest_id: str,
    issuer_id: str,
    key_id: str,
    provider: str,
    models: tuple[str, ...],
    adapter_id: str,
    adapter_version: str,
    issued_at_epoch: int,
    effective_epoch: int,
    valid_until_epoch: int | None,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_provider_manifest.v0.9",
        "manifest_id": manifest_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "provider": provider,
        "models": list(models),
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "issued_at_epoch": issued_at_epoch,
        "effective_epoch": effective_epoch,
        "valid_until_epoch": valid_until_epoch,
    }


def lease_renewal_signature_payload(
    *,
    renewal_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    activation_state_sha256: str,
    current_lease_sha256: str,
    new_valid_through_epoch: int,
    issued_at_epoch: int,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_lease_renewal.v0.9",
        "renewal_id": renewal_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "target_grant_sha256": target_grant_sha256,
        "activation_state_sha256": activation_state_sha256,
        "current_lease_sha256": current_lease_sha256,
        "new_valid_through_epoch": new_valid_through_epoch,
        "issued_at_epoch": issued_at_epoch,
    }


def build_trust_transition(
    *,
    transition_id: str,
    issuer_id: str,
    key_id: str,
    action: str,
    issued_at_epoch: int,
    effective_epoch: int,
    reason: str,
    replacement_anchor: ReflexAuthorityTrustAnchor | None,
    signature_b64: str,
) -> ReflexTrustTransition:
    payload = trust_transition_signature_payload(
        transition_id=transition_id,
        issuer_id=issuer_id,
        key_id=key_id,
        action=action,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        reason=reason,
        replacement_anchor=replacement_anchor,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexTrustTransition(
        schema="phios.reflex_trust_transition.v0.9",
        transition_id=transition_id,
        issuer_id=issuer_id,
        key_id=key_id,
        action=action,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        reason=reason,
        replacement_anchor=replacement_anchor,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_trust_transition_shape(result)
    return result


def build_ledger_checkpoint(
    *,
    checkpoint_id: str,
    issuer_id: str,
    key_id: str,
    created_at_epoch: int,
    ledger_entry_count: int,
    ledger_head_sha256: str | None,
    control_sha256: str,
    signature_b64: str,
) -> ReflexLedgerCheckpoint:
    payload = ledger_checkpoint_signature_payload(
        checkpoint_id=checkpoint_id,
        issuer_id=issuer_id,
        key_id=key_id,
        created_at_epoch=created_at_epoch,
        ledger_entry_count=ledger_entry_count,
        ledger_head_sha256=ledger_head_sha256,
        control_sha256=control_sha256,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexLedgerCheckpoint(
        schema="phios.reflex_ledger_checkpoint.v0.9",
        checkpoint_id=checkpoint_id,
        issuer_id=issuer_id,
        key_id=key_id,
        created_at_epoch=created_at_epoch,
        ledger_entry_count=ledger_entry_count,
        ledger_head_sha256=ledger_head_sha256,
        control_sha256=control_sha256,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_checkpoint_shape(result)
    return result


def build_grant_use_policy(
    *,
    policy_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    max_activations: int,
    issued_at_epoch: int,
    effective_epoch: int,
    signature_b64: str,
) -> ReflexGrantUsePolicy:
    payload = grant_use_policy_signature_payload(
        policy_id=policy_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        max_activations=max_activations,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexGrantUsePolicy(
        schema="phios.reflex_grant_use_policy.v0.9",
        policy_id=policy_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        max_activations=max_activations,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_grant_use_policy_shape(result)
    return result


def build_provider_manifest(
    *,
    manifest_id: str,
    issuer_id: str,
    key_id: str,
    provider: str,
    models: tuple[str, ...],
    adapter_id: str,
    adapter_version: str,
    issued_at_epoch: int,
    effective_epoch: int,
    valid_until_epoch: int | None,
    signature_b64: str,
) -> ReflexProviderManifest:
    payload = provider_manifest_signature_payload(
        manifest_id=manifest_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider=provider,
        models=models,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        valid_until_epoch=valid_until_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexProviderManifest(
        schema="phios.reflex_provider_manifest.v0.9",
        manifest_id=manifest_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider=provider,
        models=models,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        valid_until_epoch=valid_until_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_provider_manifest_shape(result)
    return result


def build_lease_renewal(
    *,
    renewal_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    activation_state_sha256: str,
    current_lease_sha256: str,
    new_valid_through_epoch: int,
    issued_at_epoch: int,
    signature_b64: str,
) -> ReflexLeaseRenewal:
    payload = lease_renewal_signature_payload(
        renewal_id=renewal_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        activation_state_sha256=activation_state_sha256,
        current_lease_sha256=current_lease_sha256,
        new_valid_through_epoch=new_valid_through_epoch,
        issued_at_epoch=issued_at_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexLeaseRenewal(
        schema="phios.reflex_lease_renewal.v0.9",
        renewal_id=renewal_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        activation_state_sha256=activation_state_sha256,
        current_lease_sha256=current_lease_sha256,
        new_valid_through_epoch=new_valid_through_epoch,
        issued_at_epoch=issued_at_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_lease_renewal_shape(result)
    return result


def trust_transition_from_payload(payload: Mapping[str, Any]) -> ReflexTrustTransition:
    if payload.get("schema") != "phios.reflex_trust_transition.v0.9":
        raise ReflexLifecycleContractError("unsupported trust-transition schema")
    replacement_obj = payload.get("replacement_anchor")
    replacement = (
        trust_anchor_from_payload(replacement_obj)
        if isinstance(replacement_obj, dict)
        else None
    )
    return ReflexTrustTransition(
        schema=str(payload["schema"]),
        transition_id=str(payload.get("transition_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        action=str(payload.get("action", "")),
        issued_at_epoch=_epoch_value(payload.get("issued_at_epoch"), "issued_at_epoch"),
        effective_epoch=_epoch_value(payload.get("effective_epoch"), "effective_epoch"),
        reason=str(payload.get("reason", "")),
        replacement_anchor=replacement,
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def ledger_checkpoint_from_payload(payload: Mapping[str, Any]) -> ReflexLedgerCheckpoint:
    if payload.get("schema") != "phios.reflex_ledger_checkpoint.v0.9":
        raise ReflexLifecycleContractError("unsupported ledger-checkpoint schema")
    head = payload.get("ledger_head_sha256")
    return ReflexLedgerCheckpoint(
        schema=str(payload["schema"]),
        checkpoint_id=str(payload.get("checkpoint_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        created_at_epoch=_epoch_value(payload.get("created_at_epoch"), "created_at_epoch"),
        ledger_entry_count=_nonnegative_int(
            payload.get("ledger_entry_count"), "ledger_entry_count"
        ),
        ledger_head_sha256=str(head) if head is not None else None,
        control_sha256=str(payload.get("control_sha256", "")),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def grant_use_policy_from_payload(payload: Mapping[str, Any]) -> ReflexGrantUsePolicy:
    if payload.get("schema") != "phios.reflex_grant_use_policy.v0.9":
        raise ReflexLifecycleContractError("unsupported grant-use-policy schema")
    return ReflexGrantUsePolicy(
        schema=str(payload["schema"]),
        policy_id=str(payload.get("policy_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        target_grant_sha256=str(payload.get("target_grant_sha256", "")),
        max_activations=_positive_int(payload.get("max_activations"), "max_activations"),
        issued_at_epoch=_epoch_value(payload.get("issued_at_epoch"), "issued_at_epoch"),
        effective_epoch=_epoch_value(payload.get("effective_epoch"), "effective_epoch"),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def provider_manifest_from_payload(payload: Mapping[str, Any]) -> ReflexProviderManifest:
    if payload.get("schema") != "phios.reflex_provider_manifest.v0.9":
        raise ReflexLifecycleContractError("unsupported provider-manifest schema")
    valid_until = payload.get("valid_until_epoch")
    models_obj = payload.get("models")
    if not isinstance(models_obj, list):
        raise ReflexLifecycleContractError("provider manifest models must be a list")
    return ReflexProviderManifest(
        schema=str(payload["schema"]),
        manifest_id=str(payload.get("manifest_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        provider=str(payload.get("provider", "")),
        models=tuple(str(item) for item in models_obj),
        adapter_id=str(payload.get("adapter_id", "")),
        adapter_version=str(payload.get("adapter_version", "")),
        issued_at_epoch=_epoch_value(payload.get("issued_at_epoch"), "issued_at_epoch"),
        effective_epoch=_epoch_value(payload.get("effective_epoch"), "effective_epoch"),
        valid_until_epoch=(
            _epoch_value(valid_until, "valid_until_epoch")
            if valid_until is not None
            else None
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def lease_renewal_from_payload(payload: Mapping[str, Any]) -> ReflexLeaseRenewal:
    if payload.get("schema") != "phios.reflex_lease_renewal.v0.9":
        raise ReflexLifecycleContractError("unsupported lease-renewal schema")
    return ReflexLeaseRenewal(
        schema=str(payload["schema"]),
        renewal_id=str(payload.get("renewal_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        target_grant_sha256=str(payload.get("target_grant_sha256", "")),
        activation_state_sha256=str(payload.get("activation_state_sha256", "")),
        current_lease_sha256=str(payload.get("current_lease_sha256", "")),
        new_valid_through_epoch=_epoch_value(
            payload.get("new_valid_through_epoch"), "new_valid_through_epoch"
        ),
        issued_at_epoch=_epoch_value(payload.get("issued_at_epoch"), "issued_at_epoch"),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def _validate_trust_transition_shape(item: ReflexTrustTransition) -> None:
    _safe_id(item.transition_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    if item.action not in {"ROTATE", "DISABLE"}:
        raise ReflexLifecycleContractError("trust transition action must be ROTATE or DISABLE")
    if item.effective_epoch < item.issued_at_epoch:
        raise ReflexLifecycleContractError("transition effective epoch cannot precede issue")
    if not item.reason.strip():
        raise ReflexLifecycleContractError("trust transition reason must be non-empty")
    if item.action == "ROTATE":
        if item.replacement_anchor is None:
            raise ReflexLifecycleContractError("rotation requires replacement anchor")
        if item.replacement_anchor.issuer_id != item.issuer_id:
            raise ReflexLifecycleContractError("replacement anchor must keep issuer_id")
        if item.replacement_anchor.key_id == item.key_id:
            raise ReflexLifecycleContractError("replacement key_id must differ")
        if PURPOSE_TRUST_TRANSITION not in item.replacement_anchor.allowed_purposes:
            raise ReflexLifecycleContractError(
                "replacement anchor must retain trust-transition purpose"
            )
    elif item.replacement_anchor is not None:
        raise ReflexLifecycleContractError("disable transition cannot include replacement anchor")
    _validate_envelope_hash(item.to_dict(), "envelope_sha256")


def _validate_checkpoint_shape(item: ReflexLedgerCheckpoint) -> None:
    _safe_id(item.checkpoint_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    if item.ledger_head_sha256 is not None:
        _require_sha256(item.ledger_head_sha256, "ledger_head_sha256")
    _require_sha256(item.control_sha256, "control_sha256")
    _validate_envelope_hash(item.to_dict(), "envelope_sha256")


def _validate_grant_use_policy_shape(item: ReflexGrantUsePolicy) -> None:
    _safe_id(item.policy_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    _require_sha256(item.target_grant_sha256, "target_grant_sha256")
    if item.effective_epoch < item.issued_at_epoch:
        raise ReflexLifecycleContractError("use policy effective epoch cannot precede issue")
    _validate_envelope_hash(item.to_dict(), "envelope_sha256")


def _validate_provider_manifest_shape(item: ReflexProviderManifest) -> None:
    _safe_id(item.manifest_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    if not item.provider.strip() or not item.adapter_id.strip() or not item.adapter_version.strip():
        raise ReflexLifecycleContractError("provider manifest identity fields must be non-empty")
    if not item.models or any(not model.strip() for model in item.models):
        raise ReflexLifecycleContractError("provider manifest models must be non-empty")
    if len(set(item.models)) != len(item.models):
        raise ReflexLifecycleContractError("provider manifest models must be unique")
    if item.effective_epoch < item.issued_at_epoch:
        raise ReflexLifecycleContractError("manifest effective epoch cannot precede issue")
    if item.valid_until_epoch is not None and item.valid_until_epoch <= item.effective_epoch:
        raise ReflexLifecycleContractError("manifest expiry must follow effective epoch")
    _validate_envelope_hash(item.to_dict(), "envelope_sha256")


def _validate_lease_renewal_shape(item: ReflexLeaseRenewal) -> None:
    _safe_id(item.renewal_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    _require_sha256(item.target_grant_sha256, "target_grant_sha256")
    _require_sha256(item.activation_state_sha256, "activation_state_sha256")
    _require_sha256(item.current_lease_sha256, "current_lease_sha256")
    _validate_envelope_hash(item.to_dict(), "envelope_sha256")


def _read_typed_dir(path: Path, parser: Any, validator: Any) -> list[Any]:
    if not path.exists():
        return []
    result = []
    for file_path in sorted(path.glob("*.json")):
        item = parser(_read_object(file_path))
        validator(item)
        result.append(item)
    return result


def _idempotent_write(path: Path, payload: Mapping[str, Any], digest: str) -> None:
    if path.exists():
        existing = _read_object(path)
        if existing.get("envelope_sha256") != digest:
            raise ReflexLifecycleContractError(
                f"{path.stem} already exists with different authenticated contents"
            )
        return
    _atomic_write_json(path, dict(payload))


def _activation_sha(result: Mapping[str, Any]) -> str:
    activation = result.get("activation")
    if not isinstance(activation, dict):
        raise ReflexLifecycleContractError("activation result omitted state")
    value = str(activation.get("state_sha256", ""))
    _require_sha256(value, "activation state_sha256")
    return value


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReflexLifecycleContractError(f"invalid lifecycle JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ReflexLifecycleContractError(f"{path.name} must contain a JSON object")
    return dict(value)


def _validate_envelope_hash(payload: Mapping[str, Any], field: str) -> None:
    expected = dict(payload)
    digest = str(expected.pop(field, ""))
    _require_sha256(digest, field)
    if _digest(expected) != digest:
        raise ReflexLifecycleContractError(f"{field} does not match contents")


def _safe_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", normalized):
        raise ReflexLifecycleContractError("lifecycle identifier contains unsupported characters")
    return normalized


def _epoch(value: int) -> int:
    return _epoch_value(value, "evaluation_epoch")


def _epoch_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexLifecycleContractError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReflexLifecycleContractError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexLifecycleContractError(f"{label} must be a non-negative integer")
    return value


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexLifecycleContractError(f"{label} must be a SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexLifecycleContractError(
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
        raise ReflexLifecycleContractError(
            "lifecycle payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
