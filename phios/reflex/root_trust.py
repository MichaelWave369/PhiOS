"""PhiReflex v0.10 root-of-trust hardening and offline attestation.

v0.10 composes on v0.9 without widening routing influence. It adds an
explicit trust-pin backend, exact runtime adapter artifact digests, signed
single-use activation nonces, signed recovery bundles, and offline checkpoint
bundle verification.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from phios.reflex.authority import (
    PURPOSE_ACTIVATION_NONCE,
    PURPOSE_LEDGER_CHECKPOINT,
    PURPOSE_PROVIDER_CODE_ATTESTATION,
    PURPOSE_TRUST_RECOVERY,
    ReflexAuthorityContractError,
    ReflexAuthorityPlane,
    ReflexAuthorityTrustAnchor,
    canonical_authority_bytes,
    trust_anchor_from_payload,
    _atomic_write_json,
    _digest,
    _read_object,
    _require_sha256,
    _safe_id,
    _validate_trust_anchor,
    _verify_ed25519,
)
from phios.reflex.coordination import runtime_locked
from phios.reflex.lifecycle import (
    ReflexGrantUsePolicy,
    ReflexLifecycleContractError,
    ReflexProviderManifest,
    ReflexTrustLifecyclePlane,
    ledger_checkpoint_from_payload,
    provider_manifest_from_payload,
    _validate_checkpoint_shape,
)
from phios.reflex.models import ReflexInput
from phios.reflex.providers.base import ReflexProvider
from phios.reflex.runtime_influence import (
    ReflexActivationRequest,
    ReflexRoutingInfluenceSignal,
)


class ReflexRootTrustContractError(ValueError):
    """Raised when v0.10 root-trust or attestation evidence is invalid."""


@dataclass(frozen=True, slots=True)
class ReflexTrustPinRecord:
    schema: str
    backend_id: str
    issuer_id: str
    key_id: str
    anchor_sha256: str
    pin_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "backend_id": self.backend_id,
            "issuer_id": self.issuer_id,
            "key_id": self.key_id,
            "anchor_sha256": self.anchor_sha256,
            "pin_sha256": self.pin_sha256,
        }


class TrustPinBackend(Protocol):
    """Backend contract for trust-anchor pinning."""

    backend_id: str

    def pin(self, anchor: ReflexAuthorityTrustAnchor) -> ReflexTrustPinRecord:
        ...

    def verify(self, anchor: ReflexAuthorityTrustAnchor) -> bool:
        ...

    def unpin(self, *, issuer_id: str, key_id: str) -> None:
        ...

    def list_pins(self) -> list[ReflexTrustPinRecord]:
        ...


class FileTrustPinBackend:
    """Reference pin backend.

    This detects anchor drift but shares the host filesystem trust boundary.
    It is intentionally not described as hardware-backed.
    """

    backend_id = "file-sha256-v0.10"

    def __init__(self, root: Path) -> None:
        self.root = root

    def pin(self, anchor: ReflexAuthorityTrustAnchor) -> ReflexTrustPinRecord:
        payload: dict[str, object] = {
            "schema": "phios.reflex_trust_pin.v0.10",
            "backend_id": self.backend_id,
            "issuer_id": anchor.issuer_id,
            "key_id": anchor.key_id,
            "anchor_sha256": anchor.anchor_sha256,
        }
        record = ReflexTrustPinRecord(
            schema="phios.reflex_trust_pin.v0.10",
            backend_id=self.backend_id,
            issuer_id=anchor.issuer_id,
            key_id=anchor.key_id,
            anchor_sha256=anchor.anchor_sha256,
            pin_sha256=_digest(payload),
        )
        path = self._path(anchor.issuer_id, anchor.key_id)
        if path.exists():
            existing = trust_pin_from_payload(_read_object(path))
            if existing.pin_sha256 != record.pin_sha256:
                raise ReflexRootTrustContractError(
                    "trust pin already exists with different anchor digest"
                )
            return existing
        _atomic_write_json(path, record.to_dict())
        return record

    def verify(self, anchor: ReflexAuthorityTrustAnchor) -> bool:
        path = self._path(anchor.issuer_id, anchor.key_id)
        if not path.exists():
            return False
        try:
            record = trust_pin_from_payload(_read_object(path))
        except (ReflexRootTrustContractError, ReflexAuthorityContractError):
            return False
        return (
            record.backend_id == self.backend_id
            and record.anchor_sha256 == anchor.anchor_sha256
        )

    def unpin(self, *, issuer_id: str, key_id: str) -> None:
        path = self._path(issuer_id, key_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def list_pins(self) -> list[ReflexTrustPinRecord]:
        if not self.root.exists():
            return []
        result: list[ReflexTrustPinRecord] = []
        for path in sorted(self.root.glob("*.json")):
            result.append(trust_pin_from_payload(_read_object(path)))
        return result

    def _path(self, issuer_id: str, key_id: str) -> Path:
        return self.root / f"{_safe_id(issuer_id)}__{_safe_id(key_id)}.json"


@dataclass(frozen=True, slots=True)
class ReflexProviderCodeAttestation:
    schema: str
    attestation_id: str
    issuer_id: str
    key_id: str
    provider_manifest_sha256: str
    adapter_id: str
    adapter_version: str
    artifact_name: str
    artifact_sha256: str
    issued_at_epoch: int
    valid_until_epoch: int | None
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return provider_code_attestation_signature_payload(
            attestation_id=self.attestation_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            provider_manifest_sha256=self.provider_manifest_sha256,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            artifact_name=self.artifact_name,
            artifact_sha256=self.artifact_sha256,
            issued_at_epoch=self.issued_at_epoch,
            valid_until_epoch=self.valid_until_epoch,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexActivationNonce:
    schema: str
    nonce_id: str
    issuer_id: str
    key_id: str
    target_grant_sha256: str
    activation_request_sha256: str
    issued_at_epoch: int
    valid_until_epoch: int
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return activation_nonce_signature_payload(
            nonce_id=self.nonce_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            target_grant_sha256=self.target_grant_sha256,
            activation_request_sha256=self.activation_request_sha256,
            issued_at_epoch=self.issued_at_epoch,
            valid_until_epoch=self.valid_until_epoch,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ReflexTrustRecoveryBundle:
    schema: str
    recovery_id: str
    recovery_issuer_id: str
    recovery_key_id: str
    target_issuer_id: str
    prior_anchor_sha256: str
    replacement_anchor: ReflexAuthorityTrustAnchor
    checkpoint_envelope_sha256: str
    issued_at_epoch: int
    effective_epoch: int
    reason: str
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return trust_recovery_signature_payload(
            recovery_id=self.recovery_id,
            recovery_issuer_id=self.recovery_issuer_id,
            recovery_key_id=self.recovery_key_id,
            target_issuer_id=self.target_issuer_id,
            prior_anchor_sha256=self.prior_anchor_sha256,
            replacement_anchor=self.replacement_anchor,
            checkpoint_envelope_sha256=self.checkpoint_envelope_sha256,
            issued_at_epoch=self.issued_at_epoch,
            effective_epoch=self.effective_epoch,
            reason=self.reason,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


class ReflexRootTrustPlane:
    """v0.10 root-trust wrapper around v0.9 lifecycle governance."""

    def __init__(
        self,
        *,
        lifecycle: ReflexTrustLifecyclePlane | None = None,
        authority: ReflexAuthorityPlane | None = None,
        root: Path | None = None,
        pin_backend: TrustPinBackend | None = None,
    ) -> None:
        self.lifecycle = lifecycle or ReflexTrustLifecyclePlane(root=root)
        self.authority = authority or self.lifecycle.authority
        self.control = self.lifecycle.control
        self.root = self.control.root / "root-trust"
        self.pin_backend = pin_backend or FileTrustPinBackend(self.root / "pins")
        self._runtime_lock = self.control._runtime_lock

    @property
    def code_attestations_dir(self) -> Path:
        return self.root / "provider-code-attestations"

    @property
    def nonces_dir(self) -> Path:
        return self.root / "activation-nonces"

    @property
    def nonce_states_dir(self) -> Path:
        return self.root / "nonce-state"

    @property
    def recoveries_dir(self) -> Path:
        return self.root / "recoveries"

    @runtime_locked
    def status(
        self,
        *,
        evaluation_epoch: int,
        adapter_id: str | None = None,
        adapter_version: str | None = None,
        adapter_artifact_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        recovered = self._recover_reserved_nonces(epoch)
        enforcement = self._enforce_root_trust(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            adapter_artifact_sha256=adapter_artifact_sha256,
        )
        lifecycle_status = self.lifecycle.status(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        return {
            "ok": True,
            "evaluation_epoch": epoch,
            "routing_influence_active": lifecycle_status.get(
                "routing_influence_active", False
            ),
            "root_enforcement": enforcement,
            "reserved_nonces_burned": recovered,
            "pin_backend_id": self.pin_backend.backend_id,
            "pins": [item.to_dict() for item in self.pin_backend.list_pins()],
            "code_attestations": [
                item.to_dict() for item in self._list_code_attestations()
            ],
            "nonces": [
                {
                    "nonce": item.to_dict(),
                    "state": self._nonce_state(item.nonce_id),
                }
                for item in self._list_nonces()
            ],
            "recoveries": [item.to_dict() for item in self._list_recoveries()],
            "lifecycle": lifecycle_status,
        }

    @runtime_locked
    def pin_trust_anchor(
        self,
        *,
        issuer_id: str,
        key_id: str,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        anchor = self.authority.require_trust_anchor(
            issuer_id=issuer_id,
            key_id=key_id,
        )
        record = self.pin_backend.pin(anchor)
        receipt = self._receipt(
            status="TRUST_ANCHOR_PINNED",
            reason="explicit_root_of_trust_pin",
            epoch=epoch,
            related_sha=record.pin_sha256,
        )
        self.control.append_audit_receipt(
            kind="root_trust",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {"ok": True, "pin": record.to_dict(), "receipt": receipt}

    @runtime_locked
    def ingest_provider_code_attestation(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        attestation = provider_code_attestation_from_payload(payload)
        _validate_code_attestation(attestation)
        if attestation.issued_at_epoch > epoch:
            raise ReflexRootTrustContractError(
                "code attestation cannot be ingested before issued_at_epoch"
            )
        self._require_pinned_live_key(
            attestation.issuer_id,
            attestation.key_id,
            epoch,
        )
        self.authority.verify_signed_payload(
            issuer_id=attestation.issuer_id,
            key_id=attestation.key_id,
            purpose=PURPOSE_PROVIDER_CODE_ATTESTATION,
            payload=attestation.signing_payload(),
            signature_b64=attestation.signature_b64,
        )
        manifest = self._find_manifest_by_sha(
            attestation.provider_manifest_sha256
        )
        if manifest is None or manifest.issuer_id != attestation.issuer_id:
            raise ReflexRootTrustContractError(
                "code attestation must bind an authenticated manifest from same issuer"
            )
        if (
            manifest.adapter_id != attestation.adapter_id
            or manifest.adapter_version != attestation.adapter_version
        ):
            raise ReflexRootTrustContractError(
                "code attestation adapter identity differs from provider manifest"
            )
        path = self.code_attestations_dir / (
            f"{_safe_id(attestation.attestation_id)}.json"
        )
        _idempotent_write(path, attestation.to_dict(), attestation.envelope_sha256)
        receipt = self._receipt(
            status="PROVIDER_CODE_ATTESTATION_INGESTED",
            reason="signed_adapter_artifact_digest_persisted",
            epoch=epoch,
            related_sha=attestation.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="code_attestation",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {
            "ok": True,
            "attestation": attestation.to_dict(),
            "receipt": receipt,
        }

    @runtime_locked
    def ingest_activation_nonce(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        nonce = activation_nonce_from_payload(payload)
        _validate_activation_nonce(nonce)
        if nonce.issued_at_epoch > epoch:
            raise ReflexRootTrustContractError(
                "activation nonce cannot be ingested before issued_at_epoch"
            )
        self._require_pinned_live_key(nonce.issuer_id, nonce.key_id, epoch)
        self.authority.verify_signed_payload(
            issuer_id=nonce.issuer_id,
            key_id=nonce.key_id,
            purpose=PURPOSE_ACTIVATION_NONCE,
            payload=nonce.signing_payload(),
            signature_b64=nonce.signature_b64,
        )
        envelope = self.authority.find_signed_grant_by_sha256(
            nonce.target_grant_sha256
        )
        if envelope is None or envelope.issuer_id != nonce.issuer_id:
            raise ReflexRootTrustContractError(
                "activation nonce targets unknown or different-issuer grant"
            )
        path = self.nonces_dir / f"{_safe_id(nonce.nonce_id)}.json"
        _idempotent_write(path, nonce.to_dict(), nonce.envelope_sha256)
        state_path = self.nonce_states_dir / f"{_safe_id(nonce.nonce_id)}.json"
        if not state_path.exists():
            self._write_nonce_state(
                nonce_id=nonce.nonce_id,
                nonce_sha256=nonce.envelope_sha256,
                state="AVAILABLE",
                epoch=epoch,
                activation_state_sha256=None,
            )
        receipt = self._receipt(
            status="ACTIVATION_NONCE_INGESTED",
            reason="signed_single_use_nonce_available",
            epoch=epoch,
            related_sha=nonce.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="nonce",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {
            "ok": True,
            "nonce": nonce.to_dict(),
            "state": self._nonce_state(nonce.nonce_id),
            "receipt": receipt,
        }

    @runtime_locked
    def activate_verified(
        self,
        *,
        request: ReflexActivationRequest,
        grant_id: str,
        nonce_id: str,
        adapter_id: str,
        adapter_version: str,
        adapter_artifact_sha256: str,
        evaluation_epoch: int,
        lease_until_epoch: int | None = None,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._recover_reserved_nonces(epoch)
        _require_sha256(adapter_artifact_sha256, "adapter_artifact_sha256")
        envelope = self.authority.find_signed_grant_by_id(grant_id)
        if envelope is None:
            raise ReflexRootTrustContractError(
                "authenticated activation grant is not present"
            )
        self._require_pinned_live_key(envelope.issuer_id, envelope.key_id, epoch)

        manifest = self.lifecycle.require_provider_manifest(
            grant_id=grant_id,
            provider=request.provider,
            models=request.models,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            evaluation_epoch=epoch,
        )
        self._require_pinned_live_key(manifest.issuer_id, manifest.key_id, epoch)
        use_policy = self.lifecycle.require_grant_use_policy(
            grant_sha256=envelope.grant.grant_sha256,
            evaluation_epoch=epoch,
        )
        self._require_pinned_live_key(
            use_policy.issuer_id,
            use_policy.key_id,
            epoch,
        )
        self._require_code_attestation(
            manifest=manifest,
            adapter_artifact_sha256=adapter_artifact_sha256,
            evaluation_epoch=epoch,
        )
        nonce = self._require_nonce(
            nonce_id=nonce_id,
            grant_sha256=envelope.grant.grant_sha256,
            request_sha256=request.request_sha256,
            evaluation_epoch=epoch,
        )
        self._reserve_nonce(nonce, epoch)
        try:
            result = self.lifecycle.activate_verified(
                request=request,
                grant_id=grant_id,
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                evaluation_epoch=epoch,
                lease_until_epoch=lease_until_epoch,
                expected_control_sha256=expected_control_sha256,
            )
        except Exception:
            self._finalize_nonce(
                nonce,
                state="BURNED",
                epoch=epoch,
                activation_state_sha256=None,
            )
            raise

        activation = result.get("activation")
        activation_sha = (
            str(activation.get("state_sha256"))
            if isinstance(activation, dict)
            and isinstance(activation.get("state_sha256"), str)
            else None
        )
        if result.get("ok") is True:
            self._finalize_nonce(
                nonce,
                state="CONSUMED",
                epoch=epoch,
                activation_state_sha256=activation_sha,
            )
        else:
            self._finalize_nonce(
                nonce,
                state="BURNED",
                epoch=epoch,
                activation_state_sha256=activation_sha,
            )
        result["activation_nonce"] = {
            "nonce_id": nonce.nonce_id,
            "state": self._nonce_state(nonce.nonce_id),
        }
        return result

    @runtime_locked
    def evaluate_active(
        self,
        *,
        reflex_input: ReflexInput,
        baseline_provider: ReflexProvider,
        influence_provider: ReflexProvider,
        adapter_id: str,
        adapter_version: str,
        adapter_artifact_sha256: str,
        evaluation_epoch: int,
    ) -> tuple[ReflexRoutingInfluenceSignal | None, dict[str, Any]]:
        epoch = _epoch(evaluation_epoch)
        enforcement = self._enforce_root_trust(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            adapter_artifact_sha256=adapter_artifact_sha256,
        )
        if enforcement is not None:
            return None, enforcement
        return self.lifecycle.evaluate_active(
            reflex_input=reflex_input,
            baseline_provider=baseline_provider,
            influence_provider=influence_provider,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            evaluation_epoch=epoch,
        )

    @runtime_locked
    def apply_trust_recovery(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        recovery = trust_recovery_from_payload(payload)
        _validate_recovery(recovery)
        if recovery.issued_at_epoch > epoch:
            raise ReflexRootTrustContractError(
                "recovery bundle cannot be used before issued_at_epoch"
            )
        if recovery.effective_epoch > epoch:
            raise ReflexRootTrustContractError(
                "recovery bundle is not effective yet"
            )
        self._require_pinned_live_key(
            recovery.recovery_issuer_id,
            recovery.recovery_key_id,
            epoch,
        )
        self.authority.verify_signed_payload(
            issuer_id=recovery.recovery_issuer_id,
            key_id=recovery.recovery_key_id,
            purpose=PURPOSE_TRUST_RECOVERY,
            payload=recovery.signing_payload(),
            signature_b64=recovery.signature_b64,
        )
        prior = self._find_anchor_by_sha(recovery.prior_anchor_sha256)
        if prior is None or prior.issuer_id != recovery.target_issuer_id:
            raise ReflexRootTrustContractError(
                "recovery prior anchor does not match current trust store"
            )
        if not self.pin_backend.verify(prior):
            raise ReflexRootTrustContractError(
                "recovery prior anchor is not the currently pinned root"
            )
        if recovery.replacement_anchor.issuer_id != recovery.target_issuer_id:
            raise ReflexRootTrustContractError(
                "recovery replacement cannot change target issuer"
            )
        if recovery.replacement_anchor.anchor_sha256 == prior.anchor_sha256:
            raise ReflexRootTrustContractError(
                "recovery replacement must change anchor"
            )
        _validate_trust_anchor(recovery.replacement_anchor)
        if not self._checkpoint_exists(recovery.checkpoint_envelope_sha256):
            raise ReflexRootTrustContractError(
                "recovery references unknown signed checkpoint"
            )

        self.authority.ingest_trust_anchor(
            recovery.replacement_anchor.to_dict(),
            evaluation_epoch=epoch,
        )
        new_pin = self.pin_backend.pin(recovery.replacement_anchor)
        self.pin_backend.unpin(
            issuer_id=prior.issuer_id,
            key_id=prior.key_id,
        )
        collapse = self._collapse_if_grant_key(
            issuer_id=prior.issuer_id,
            key_id=prior.key_id,
            evaluation_epoch=epoch,
            reason="v0_10_root_recovery_retired_prior_pin",
        )
        path = self.recoveries_dir / f"{_safe_id(recovery.recovery_id)}.json"
        _idempotent_write(path, recovery.to_dict(), recovery.envelope_sha256)
        receipt = self._receipt(
            status="TRUST_RECOVERY_APPLIED",
            reason="signed_recovery_replaced_pinned_root",
            epoch=epoch,
            related_sha=recovery.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="recovery",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {
            "ok": True,
            "recovery": recovery.to_dict(),
            "new_pin": new_pin.to_dict(),
            "collapse": collapse,
            "receipt": receipt,
        }

    @runtime_locked
    def export_checkpoint_bundle(
        self,
        *,
        checkpoint_id: str,
    ) -> dict[str, Any]:
        checkpoint = self._find_checkpoint_by_id(checkpoint_id)
        if checkpoint is None:
            raise ReflexRootTrustContractError("checkpoint not found")
        anchor = self.authority.require_trust_anchor(
            issuer_id=checkpoint.issuer_id,
            key_id=checkpoint.key_id,
        )
        payload: dict[str, object] = {
            "schema": "phios.reflex_offline_checkpoint_bundle.v0.10",
            "checkpoint": checkpoint.to_dict(),
            "trust_anchor": anchor.to_dict(),
        }
        payload["bundle_sha256"] = _digest(payload)
        return payload

    def _enforce_root_trust(
        self,
        *,
        evaluation_epoch: int,
        adapter_id: str | None,
        adapter_version: str | None,
        adapter_artifact_sha256: str | None,
    ) -> dict[str, Any] | None:
        lifecycle_status = self.lifecycle.status(
            evaluation_epoch=evaluation_epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        authority_obj = lifecycle_status.get("authority")
        authority_status = authority_obj if isinstance(authority_obj, dict) else {}
        control_obj = authority_status.get("control")
        control = control_obj if isinstance(control_obj, dict) else {}
        activation_obj = control.get("activation")
        activation = activation_obj if isinstance(activation_obj, dict) else None
        if (
            activation is None
            or activation.get("routing_influence_active") is not True
        ):
            return None

        grant_sha = str(activation.get("activated_by_grant_sha256", ""))
        envelope = self.authority.find_signed_grant_by_sha256(grant_sha)
        try:
            if envelope is None:
                raise ReflexRootTrustContractError(
                    "active grant has no authenticated envelope"
                )
            self._require_pinned_live_key(
                envelope.issuer_id,
                envelope.key_id,
                evaluation_epoch,
            )
            if (
                adapter_id is None
                or adapter_version is None
                or adapter_artifact_sha256 is None
            ):
                raise ReflexRootTrustContractError(
                    "runtime adapter identity and artifact digest are required"
                )
            models_obj = activation.get("models")
            models = (
                tuple(str(item) for item in models_obj)
                if isinstance(models_obj, list)
                else ()
            )
            manifest = self.lifecycle.require_provider_manifest(
                grant_id=envelope.grant.grant_id,
                provider=str(activation.get("provider", "")),
                models=models,
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                evaluation_epoch=evaluation_epoch,
            )
            self._require_pinned_live_key(
                manifest.issuer_id,
                manifest.key_id,
                evaluation_epoch,
            )
            use_policy = self.lifecycle.require_grant_use_policy(
                grant_sha256=grant_sha,
                evaluation_epoch=evaluation_epoch,
            )
            self._require_pinned_live_key(
                use_policy.issuer_id,
                use_policy.key_id,
                evaluation_epoch,
            )
            self._require_code_attestation(
                manifest=manifest,
                adapter_artifact_sha256=adapter_artifact_sha256,
                evaluation_epoch=evaluation_epoch,
            )
        except (
            ReflexRootTrustContractError,
            ReflexLifecycleContractError,
            ReflexAuthorityContractError,
        ):
            return self.authority.deactivate(
                reason="v0_10_root_trust_or_code_attestation_invalid",
                evaluation_epoch=evaluation_epoch,
            )
        return None

    def _require_pinned_live_key(
        self,
        issuer_id: str,
        key_id: str,
        evaluation_epoch: int,
    ) -> ReflexAuthorityTrustAnchor:
        anchor = self.authority.require_trust_anchor(
            issuer_id=issuer_id,
            key_id=key_id,
        )
        if not self.pin_backend.verify(anchor):
            raise ReflexRootTrustContractError(
                "authority key is trusted but not pinned by v0.10 root backend"
            )
        if not self.lifecycle.is_key_live(
            issuer_id=issuer_id,
            key_id=key_id,
            evaluation_epoch=evaluation_epoch,
        ):
            raise ReflexRootTrustContractError(
                "pinned authority key is retired or disabled"
            )
        return anchor

    def _require_code_attestation(
        self,
        *,
        manifest: ReflexProviderManifest,
        adapter_artifact_sha256: str,
        evaluation_epoch: int,
    ) -> ReflexProviderCodeAttestation:
        _require_sha256(adapter_artifact_sha256, "adapter_artifact_sha256")
        for attestation in self._list_code_attestations():
            if attestation.issuer_id != manifest.issuer_id:
                continue
            if attestation.provider_manifest_sha256 != manifest.envelope_sha256:
                continue
            if attestation.adapter_id != manifest.adapter_id:
                continue
            if attestation.adapter_version != manifest.adapter_version:
                continue
            if attestation.artifact_sha256 != adapter_artifact_sha256:
                continue
            if evaluation_epoch < attestation.issued_at_epoch:
                continue
            if (
                attestation.valid_until_epoch is not None
                and evaluation_epoch >= attestation.valid_until_epoch
            ):
                continue
            self._require_pinned_live_key(
                attestation.issuer_id,
                attestation.key_id,
                evaluation_epoch,
            )
            self.authority.verify_signed_payload(
                issuer_id=attestation.issuer_id,
                key_id=attestation.key_id,
                purpose=PURPOSE_PROVIDER_CODE_ATTESTATION,
                payload=attestation.signing_payload(),
                signature_b64=attestation.signature_b64,
            )
            return attestation
        raise ReflexRootTrustContractError(
            "no signed provider-code attestation matches loaded adapter artifact"
        )

    def _require_nonce(
        self,
        *,
        nonce_id: str,
        grant_sha256: str,
        request_sha256: str,
        evaluation_epoch: int,
    ) -> ReflexActivationNonce:
        path = self.nonces_dir / f"{_safe_id(nonce_id)}.json"
        if not path.exists():
            raise ReflexRootTrustContractError("activation nonce not found")
        nonce = activation_nonce_from_payload(_read_object(path))
        _validate_activation_nonce(nonce)
        if nonce.target_grant_sha256 != grant_sha256:
            raise ReflexRootTrustContractError("activation nonce grant mismatch")
        if nonce.activation_request_sha256 != request_sha256:
            raise ReflexRootTrustContractError("activation nonce request mismatch")
        if evaluation_epoch < nonce.issued_at_epoch:
            raise ReflexRootTrustContractError("activation nonce is not valid yet")
        if evaluation_epoch >= nonce.valid_until_epoch:
            raise ReflexRootTrustContractError("activation nonce has expired")
        state = self._nonce_state(nonce.nonce_id)
        if state.get("state") != "AVAILABLE":
            raise ReflexRootTrustContractError("activation nonce is not available")
        self._require_pinned_live_key(nonce.issuer_id, nonce.key_id, evaluation_epoch)
        self.authority.verify_signed_payload(
            issuer_id=nonce.issuer_id,
            key_id=nonce.key_id,
            purpose=PURPOSE_ACTIVATION_NONCE,
            payload=nonce.signing_payload(),
            signature_b64=nonce.signature_b64,
        )
        return nonce

    def _reserve_nonce(self, nonce: ReflexActivationNonce, epoch: int) -> None:
        self._write_nonce_state(
            nonce_id=nonce.nonce_id,
            nonce_sha256=nonce.envelope_sha256,
            state="RESERVED",
            epoch=epoch,
            activation_state_sha256=None,
        )

    def _finalize_nonce(
        self,
        nonce: ReflexActivationNonce,
        *,
        state: str,
        epoch: int,
        activation_state_sha256: str | None,
    ) -> None:
        self._write_nonce_state(
            nonce_id=nonce.nonce_id,
            nonce_sha256=nonce.envelope_sha256,
            state=state,
            epoch=epoch,
            activation_state_sha256=activation_state_sha256,
        )
        receipt = self._receipt(
            status=f"ACTIVATION_NONCE_{state}",
            reason="single_use_nonce_finalized",
            epoch=epoch,
            related_sha=nonce.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="nonce",
            evaluation_epoch=epoch,
            receipt=receipt,
        )

    def _recover_reserved_nonces(self, epoch: int) -> int:
        if not self.nonce_states_dir.exists():
            return 0
        burned = 0
        for path in sorted(self.nonce_states_dir.glob("*.json")):
            payload = _read_object(path)
            _validate_nonce_state(payload)
            if payload.get("state") != "RESERVED":
                continue
            payload["state"] = "BURNED"
            payload["updated_epoch"] = epoch
            payload["state_sha256"] = _nonce_state_digest(payload)
            _atomic_write_json(path, payload)
            burned += 1
        return burned

    def _write_nonce_state(
        self,
        *,
        nonce_id: str,
        nonce_sha256: str,
        state: str,
        epoch: int,
        activation_state_sha256: str | None,
    ) -> None:
        if state not in {"AVAILABLE", "RESERVED", "CONSUMED", "BURNED"}:
            raise ReflexRootTrustContractError("unsupported nonce state")
        payload: dict[str, object] = {
            "schema": "phios.reflex_activation_nonce_state.v0.10",
            "nonce_id": nonce_id,
            "nonce_sha256": nonce_sha256,
            "state": state,
            "updated_epoch": epoch,
            "activation_state_sha256": activation_state_sha256,
        }
        payload["state_sha256"] = _digest(payload)
        _atomic_write_json(
            self.nonce_states_dir / f"{_safe_id(nonce_id)}.json",
            payload,
        )

    def _nonce_state(self, nonce_id: str) -> dict[str, Any]:
        path = self.nonce_states_dir / f"{_safe_id(nonce_id)}.json"
        if not path.exists():
            return {"state": "MISSING"}
        payload = _read_object(path)
        _validate_nonce_state(payload)
        return payload

    def _find_manifest_by_sha(
        self,
        envelope_sha256: str,
    ) -> ReflexProviderManifest | None:
        if not self.lifecycle.manifests_dir.exists():
            return None
        for path in sorted(self.lifecycle.manifests_dir.glob("*.json")):
            manifest = provider_manifest_from_payload(_read_object(path))
            if manifest.envelope_sha256 == envelope_sha256:
                return manifest
        return None

    def _find_anchor_by_sha(
        self,
        anchor_sha256: str,
    ) -> ReflexAuthorityTrustAnchor | None:
        if not self.authority.trust_dir.exists():
            return None
        for path in sorted(self.authority.trust_dir.glob("*.json")):
            anchor = trust_anchor_from_payload(_read_object(path))
            _validate_trust_anchor(anchor)
            if anchor.anchor_sha256 == anchor_sha256:
                return anchor
        return None

    def _checkpoint_exists(self, envelope_sha256: str) -> bool:
        if not self.lifecycle.checkpoints_dir.exists():
            return False
        for path in sorted(self.lifecycle.checkpoints_dir.glob("*.json")):
            checkpoint = ledger_checkpoint_from_payload(_read_object(path))
            _validate_checkpoint_shape(checkpoint)
            if checkpoint.envelope_sha256 == envelope_sha256:
                return True
        return False

    def _find_checkpoint_by_id(self, checkpoint_id: str):
        if not self.lifecycle.checkpoints_dir.exists():
            return None
        for path in sorted(self.lifecycle.checkpoints_dir.glob("*.json")):
            checkpoint = ledger_checkpoint_from_payload(_read_object(path))
            _validate_checkpoint_shape(checkpoint)
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    def _collapse_if_grant_key(
        self,
        *,
        issuer_id: str,
        key_id: str,
        evaluation_epoch: int,
        reason: str,
    ) -> dict[str, Any] | None:
        status = self.control.status(evaluation_epoch=evaluation_epoch)
        activation = status.get("activation")
        if not isinstance(activation, dict) or activation.get(
            "routing_influence_active"
        ) is not True:
            return None
        grant_sha = str(activation.get("activated_by_grant_sha256", ""))
        envelope = self.authority.find_signed_grant_by_sha256(grant_sha)
        if (
            envelope is not None
            and envelope.issuer_id == issuer_id
            and envelope.key_id == key_id
        ):
            return self.authority.deactivate(
                reason=reason,
                evaluation_epoch=evaluation_epoch,
            )
        return None

    def _list_code_attestations(self) -> list[ReflexProviderCodeAttestation]:
        if not self.code_attestations_dir.exists():
            return []
        return [
            provider_code_attestation_from_payload(_read_object(path))
            for path in sorted(self.code_attestations_dir.glob("*.json"))
        ]

    def _list_nonces(self) -> list[ReflexActivationNonce]:
        if not self.nonces_dir.exists():
            return []
        return [
            activation_nonce_from_payload(_read_object(path))
            for path in sorted(self.nonces_dir.glob("*.json"))
        ]

    def _list_recoveries(self) -> list[ReflexTrustRecoveryBundle]:
        if not self.recoveries_dir.exists():
            return []
        return [
            trust_recovery_from_payload(_read_object(path))
            for path in sorted(self.recoveries_dir.glob("*.json"))
        ]

    @staticmethod
    def _receipt(
        *,
        status: str,
        reason: str,
        epoch: int,
        related_sha: str,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": "phios.reflex_root_trust_receipt.v0.10",
            "status": status,
            "reason": reason,
            "evaluation_epoch": epoch,
            "related_sha256": related_sha,
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        payload["receipt_sha256"] = _digest(payload)
        return payload


def provider_artifact_identity(provider_or_type: object) -> dict[str, str]:
    """Hash the exact Python source file defining a provider adapter."""

    cls = provider_or_type if isinstance(provider_or_type, type) else type(provider_or_type)
    path_text = inspect.getsourcefile(cls) or inspect.getfile(cls)
    path = Path(path_text).resolve()
    data = path.read_bytes()
    return {
        "artifact_name": path.name,
        "artifact_sha256": hashlib.sha256(data).hexdigest(),
    }


def provider_code_attestation_signature_payload(
    *,
    attestation_id: str,
    issuer_id: str,
    key_id: str,
    provider_manifest_sha256: str,
    adapter_id: str,
    adapter_version: str,
    artifact_name: str,
    artifact_sha256: str,
    issued_at_epoch: int,
    valid_until_epoch: int | None,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_provider_code_attestation.v0.10",
        "attestation_id": attestation_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "provider_manifest_sha256": provider_manifest_sha256,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "artifact_name": artifact_name,
        "artifact_sha256": artifact_sha256,
        "issued_at_epoch": issued_at_epoch,
        "valid_until_epoch": valid_until_epoch,
    }


def activation_nonce_signature_payload(
    *,
    nonce_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    activation_request_sha256: str,
    issued_at_epoch: int,
    valid_until_epoch: int,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_activation_nonce.v0.10",
        "nonce_id": nonce_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "target_grant_sha256": target_grant_sha256,
        "activation_request_sha256": activation_request_sha256,
        "issued_at_epoch": issued_at_epoch,
        "valid_until_epoch": valid_until_epoch,
    }


def trust_recovery_signature_payload(
    *,
    recovery_id: str,
    recovery_issuer_id: str,
    recovery_key_id: str,
    target_issuer_id: str,
    prior_anchor_sha256: str,
    replacement_anchor: ReflexAuthorityTrustAnchor,
    checkpoint_envelope_sha256: str,
    issued_at_epoch: int,
    effective_epoch: int,
    reason: str,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_trust_recovery.v0.10",
        "recovery_id": recovery_id,
        "recovery_issuer_id": recovery_issuer_id,
        "recovery_key_id": recovery_key_id,
        "target_issuer_id": target_issuer_id,
        "prior_anchor_sha256": prior_anchor_sha256,
        "replacement_anchor": replacement_anchor.to_dict(),
        "checkpoint_envelope_sha256": checkpoint_envelope_sha256,
        "issued_at_epoch": issued_at_epoch,
        "effective_epoch": effective_epoch,
        "reason": reason,
    }


def build_provider_code_attestation(
    *,
    attestation_id: str,
    issuer_id: str,
    key_id: str,
    provider_manifest_sha256: str,
    adapter_id: str,
    adapter_version: str,
    artifact_name: str,
    artifact_sha256: str,
    issued_at_epoch: int,
    valid_until_epoch: int | None,
    signature_b64: str,
) -> ReflexProviderCodeAttestation:
    payload = provider_code_attestation_signature_payload(
        attestation_id=attestation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider_manifest_sha256=provider_manifest_sha256,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        artifact_name=artifact_name,
        artifact_sha256=artifact_sha256,
        issued_at_epoch=issued_at_epoch,
        valid_until_epoch=valid_until_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexProviderCodeAttestation(
        schema="phios.reflex_provider_code_attestation.v0.10",
        attestation_id=attestation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider_manifest_sha256=provider_manifest_sha256,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        artifact_name=artifact_name,
        artifact_sha256=artifact_sha256,
        issued_at_epoch=issued_at_epoch,
        valid_until_epoch=valid_until_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_code_attestation(result)
    return result


def build_activation_nonce(
    *,
    nonce_id: str,
    issuer_id: str,
    key_id: str,
    target_grant_sha256: str,
    activation_request_sha256: str,
    issued_at_epoch: int,
    valid_until_epoch: int,
    signature_b64: str,
) -> ReflexActivationNonce:
    payload = activation_nonce_signature_payload(
        nonce_id=nonce_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        activation_request_sha256=activation_request_sha256,
        issued_at_epoch=issued_at_epoch,
        valid_until_epoch=valid_until_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexActivationNonce(
        schema="phios.reflex_activation_nonce.v0.10",
        nonce_id=nonce_id,
        issuer_id=issuer_id,
        key_id=key_id,
        target_grant_sha256=target_grant_sha256,
        activation_request_sha256=activation_request_sha256,
        issued_at_epoch=issued_at_epoch,
        valid_until_epoch=valid_until_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_activation_nonce(result)
    return result


def build_trust_recovery(
    *,
    recovery_id: str,
    recovery_issuer_id: str,
    recovery_key_id: str,
    target_issuer_id: str,
    prior_anchor_sha256: str,
    replacement_anchor: ReflexAuthorityTrustAnchor,
    checkpoint_envelope_sha256: str,
    issued_at_epoch: int,
    effective_epoch: int,
    reason: str,
    signature_b64: str,
) -> ReflexTrustRecoveryBundle:
    payload = trust_recovery_signature_payload(
        recovery_id=recovery_id,
        recovery_issuer_id=recovery_issuer_id,
        recovery_key_id=recovery_key_id,
        target_issuer_id=target_issuer_id,
        prior_anchor_sha256=prior_anchor_sha256,
        replacement_anchor=replacement_anchor,
        checkpoint_envelope_sha256=checkpoint_envelope_sha256,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        reason=reason,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexTrustRecoveryBundle(
        schema="phios.reflex_trust_recovery.v0.10",
        recovery_id=recovery_id,
        recovery_issuer_id=recovery_issuer_id,
        recovery_key_id=recovery_key_id,
        target_issuer_id=target_issuer_id,
        prior_anchor_sha256=prior_anchor_sha256,
        replacement_anchor=replacement_anchor,
        checkpoint_envelope_sha256=checkpoint_envelope_sha256,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        reason=reason,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_recovery(result)
    return result


def provider_code_attestation_from_payload(
    payload: Mapping[str, Any],
) -> ReflexProviderCodeAttestation:
    return ReflexProviderCodeAttestation(
        schema=str(payload.get("schema", "")),
        attestation_id=str(payload.get("attestation_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        provider_manifest_sha256=str(payload.get("provider_manifest_sha256", "")),
        adapter_id=str(payload.get("adapter_id", "")),
        adapter_version=str(payload.get("adapter_version", "")),
        artifact_name=str(payload.get("artifact_name", "")),
        artifact_sha256=str(payload.get("artifact_sha256", "")),
        issued_at_epoch=_int(payload.get("issued_at_epoch"), "issued_at_epoch"),
        valid_until_epoch=_optional_int(
            payload.get("valid_until_epoch"),
            "valid_until_epoch",
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def activation_nonce_from_payload(
    payload: Mapping[str, Any],
) -> ReflexActivationNonce:
    return ReflexActivationNonce(
        schema=str(payload.get("schema", "")),
        nonce_id=str(payload.get("nonce_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        target_grant_sha256=str(payload.get("target_grant_sha256", "")),
        activation_request_sha256=str(
            payload.get("activation_request_sha256", "")
        ),
        issued_at_epoch=_int(payload.get("issued_at_epoch"), "issued_at_epoch"),
        valid_until_epoch=_int(
            payload.get("valid_until_epoch"),
            "valid_until_epoch",
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def trust_recovery_from_payload(
    payload: Mapping[str, Any],
) -> ReflexTrustRecoveryBundle:
    replacement_obj = payload.get("replacement_anchor")
    if not isinstance(replacement_obj, dict):
        raise ReflexRootTrustContractError(
            "trust recovery requires replacement_anchor object"
        )
    return ReflexTrustRecoveryBundle(
        schema=str(payload.get("schema", "")),
        recovery_id=str(payload.get("recovery_id", "")),
        recovery_issuer_id=str(payload.get("recovery_issuer_id", "")),
        recovery_key_id=str(payload.get("recovery_key_id", "")),
        target_issuer_id=str(payload.get("target_issuer_id", "")),
        prior_anchor_sha256=str(payload.get("prior_anchor_sha256", "")),
        replacement_anchor=trust_anchor_from_payload(replacement_obj),
        checkpoint_envelope_sha256=str(
            payload.get("checkpoint_envelope_sha256", "")
        ),
        issued_at_epoch=_int(payload.get("issued_at_epoch"), "issued_at_epoch"),
        effective_epoch=_int(payload.get("effective_epoch"), "effective_epoch"),
        reason=str(payload.get("reason", "")),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def trust_pin_from_payload(payload: Mapping[str, Any]) -> ReflexTrustPinRecord:
    record = ReflexTrustPinRecord(
        schema=str(payload.get("schema", "")),
        backend_id=str(payload.get("backend_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        anchor_sha256=str(payload.get("anchor_sha256", "")),
        pin_sha256=str(payload.get("pin_sha256", "")),
    )
    if record.schema != "phios.reflex_trust_pin.v0.10":
        raise ReflexRootTrustContractError("unsupported trust-pin schema")
    _safe_id(record.issuer_id)
    _safe_id(record.key_id)
    _require_sha256(record.anchor_sha256, "anchor_sha256")
    payload_copy = record.to_dict()
    digest = str(payload_copy.pop("pin_sha256"))
    if _digest(payload_copy) != digest:
        raise ReflexRootTrustContractError("trust-pin hash mismatch")
    return record


def verify_offline_checkpoint_bundle(
    payload: Mapping[str, Any],
    *,
    expected_anchor_sha256: str | None = None,
) -> dict[str, Any]:
    if payload.get("schema") != "phios.reflex_offline_checkpoint_bundle.v0.10":
        raise ReflexRootTrustContractError(
            "unsupported offline checkpoint bundle schema"
        )
    checkpoint_obj = payload.get("checkpoint")
    anchor_obj = payload.get("trust_anchor")
    if not isinstance(checkpoint_obj, dict) or not isinstance(anchor_obj, dict):
        raise ReflexRootTrustContractError(
            "offline checkpoint bundle is missing typed artifacts"
        )
    bundle_copy = dict(payload)
    bundle_sha = str(bundle_copy.pop("bundle_sha256", ""))
    _require_sha256(bundle_sha, "bundle_sha256")
    if _digest(bundle_copy) != bundle_sha:
        raise ReflexRootTrustContractError("offline bundle hash mismatch")

    anchor = trust_anchor_from_payload(anchor_obj)
    _validate_trust_anchor(anchor)
    checkpoint = ledger_checkpoint_from_payload(checkpoint_obj)
    _validate_checkpoint_shape(checkpoint)
    if checkpoint.issuer_id != anchor.issuer_id or checkpoint.key_id != anchor.key_id:
        raise ReflexRootTrustContractError(
            "checkpoint signer does not match bundled trust anchor"
        )
    if PURPOSE_LEDGER_CHECKPOINT not in anchor.allowed_purposes:
        raise ReflexRootTrustContractError(
            "bundled key is not authorized for ledger checkpoints"
        )
    checkpoint_payload = checkpoint.to_dict()
    envelope_sha = str(checkpoint_payload.pop("envelope_sha256"))
    if _digest(checkpoint_payload) != envelope_sha:
        raise ReflexRootTrustContractError("checkpoint envelope hash mismatch")
    _verify_ed25519(
        anchor.public_key_b64,
        canonical_authority_bytes(checkpoint.signing_payload()),
        checkpoint.signature_b64,
    )
    trusted_match = None
    if expected_anchor_sha256 is not None:
        _require_sha256(expected_anchor_sha256, "expected_anchor_sha256")
        trusted_match = anchor.anchor_sha256 == expected_anchor_sha256
        if not trusted_match:
            raise ReflexRootTrustContractError(
                "offline checkpoint anchor does not match expected pinned digest"
            )
    return {
        "ok": True,
        "bundle_sha256": bundle_sha,
        "checkpoint_envelope_sha256": checkpoint.envelope_sha256,
        "anchor_sha256": anchor.anchor_sha256,
        "expected_anchor_match": trusted_match,
        "warning": (
            None
            if expected_anchor_sha256 is not None
            else "signature valid relative to bundled key; no external pin supplied"
        ),
    }


def _validate_code_attestation(attestation: ReflexProviderCodeAttestation) -> None:
    if attestation.schema != "phios.reflex_provider_code_attestation.v0.10":
        raise ReflexRootTrustContractError(
            "unsupported provider-code attestation schema"
        )
    _safe_id(attestation.attestation_id)
    _safe_id(attestation.issuer_id)
    _safe_id(attestation.key_id)
    _require_sha256(
        attestation.provider_manifest_sha256,
        "provider_manifest_sha256",
    )
    _require_sha256(attestation.artifact_sha256, "artifact_sha256")
    if not attestation.adapter_id.strip() or not attestation.adapter_version.strip():
        raise ReflexRootTrustContractError("adapter identity is required")
    if not attestation.artifact_name.strip():
        raise ReflexRootTrustContractError("artifact_name is required")
    if (
        attestation.valid_until_epoch is not None
        and attestation.valid_until_epoch <= attestation.issued_at_epoch
    ):
        raise ReflexRootTrustContractError("code attestation validity window invalid")
    _validate_signed_envelope(attestation.to_dict())


def _validate_activation_nonce(nonce: ReflexActivationNonce) -> None:
    if nonce.schema != "phios.reflex_activation_nonce.v0.10":
        raise ReflexRootTrustContractError("unsupported activation-nonce schema")
    _safe_id(nonce.nonce_id)
    _safe_id(nonce.issuer_id)
    _safe_id(nonce.key_id)
    _require_sha256(nonce.target_grant_sha256, "target_grant_sha256")
    _require_sha256(
        nonce.activation_request_sha256,
        "activation_request_sha256",
    )
    if nonce.valid_until_epoch <= nonce.issued_at_epoch:
        raise ReflexRootTrustContractError("activation nonce validity window invalid")
    _validate_signed_envelope(nonce.to_dict())


def _validate_recovery(recovery: ReflexTrustRecoveryBundle) -> None:
    if recovery.schema != "phios.reflex_trust_recovery.v0.10":
        raise ReflexRootTrustContractError("unsupported trust-recovery schema")
    _safe_id(recovery.recovery_id)
    _safe_id(recovery.recovery_issuer_id)
    _safe_id(recovery.recovery_key_id)
    _safe_id(recovery.target_issuer_id)
    _require_sha256(recovery.prior_anchor_sha256, "prior_anchor_sha256")
    _require_sha256(
        recovery.checkpoint_envelope_sha256,
        "checkpoint_envelope_sha256",
    )
    _validate_trust_anchor(recovery.replacement_anchor)
    if not recovery.reason.strip():
        raise ReflexRootTrustContractError("trust recovery reason is required")
    if recovery.effective_epoch < recovery.issued_at_epoch:
        raise ReflexRootTrustContractError(
            "trust recovery effective_epoch cannot precede issued_at_epoch"
        )
    _validate_signed_envelope(recovery.to_dict())


def _validate_nonce_state(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != "phios.reflex_activation_nonce_state.v0.10":
        raise ReflexRootTrustContractError("unsupported activation nonce state")
    if payload.get("state") not in {
        "AVAILABLE",
        "RESERVED",
        "CONSUMED",
        "BURNED",
    }:
        raise ReflexRootTrustContractError("invalid activation nonce state")
    digest = str(payload.get("state_sha256", ""))
    _require_sha256(digest, "state_sha256")
    expected = dict(payload)
    expected.pop("state_sha256", None)
    if _digest(expected) != digest:
        raise ReflexRootTrustContractError("activation nonce state hash mismatch")


def _nonce_state_digest(payload: Mapping[str, Any]) -> str:
    expected = dict(payload)
    expected.pop("state_sha256", None)
    return _digest(expected)


def _validate_signed_envelope(payload: dict[str, object]) -> None:
    digest = str(payload.pop("envelope_sha256", ""))
    _require_sha256(digest, "envelope_sha256")
    if _digest(payload) != digest:
        raise ReflexRootTrustContractError("signed root-trust envelope hash mismatch")


def _idempotent_write(
    path: Path,
    payload: Mapping[str, object],
    envelope_sha256: str,
) -> None:
    if path.exists():
        existing = _read_object(path)
        if existing.get("envelope_sha256") != envelope_sha256:
            raise ReflexRootTrustContractError(
                "artifact ID already exists with different contents"
            )
        return
    _atomic_write_json(path, payload)


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexRootTrustContractError(
            f"{label} must be a non-negative integer"
        )
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _int(value, label)
