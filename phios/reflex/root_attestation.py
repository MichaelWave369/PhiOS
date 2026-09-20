"""PhiReflex v0.10 root pinning, artifact attestation, and replay controls.

v0.10 composes over v0.9 trust lifecycle. It adds an externally supplied
root-anchor pin, exact provider-adapter source digests, signed one-use
activation nonces, offline-verifiable checkpoint bundles, and conflict-only
replication snapshot ingestion.

The root pin is intentionally external configuration. This module does not
pretend a second local JSON file is a hardware root of trust.
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from phios.reflex.authority import (
    PURPOSE_ACTIVATION_NONCE,
    PURPOSE_LEDGER_CHECKPOINT,
    PURPOSE_PROVIDER_ARTIFACT,
    PURPOSE_REPLICATION_SNAPSHOT,
    ReflexAuthorityContractError,
    ReflexAuthorityPlane,
    ReflexAuthorityTrustAnchor,
    canonical_authority_bytes,
    trust_anchor_from_payload,
    _atomic_write_json,
    _digest,
    _epoch,
    _read_object,
    _require_sha256,
    _safe_id,
    _validate_trust_anchor,
    _verify_ed25519,
)
from phios.reflex.coordination import runtime_locked
from phios.reflex.lifecycle import (
    ReflexLifecycleContractError,
    ReflexLedgerCheckpoint,
    ReflexProviderManifest,
    ReflexTrustLifecyclePlane,
    ledger_checkpoint_from_payload,
)
from phios.reflex.models import ReflexInput
from phios.reflex.providers.base import ReflexProvider
from phios.reflex.runtime_influence import (
    ReflexActivationRequest,
    ReflexRoutingInfluenceSignal,
)


class ReflexRootAttestationContractError(ValueError):
    """Raised when v0.10 root or attestation contracts fail closed."""


@dataclass(frozen=True, slots=True)
class ReflexRootPin:
    issuer_id: str
    key_id: str
    anchor_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "issuer_id": self.issuer_id,
            "key_id": self.key_id,
            "anchor_sha256": self.anchor_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexProviderArtifactAttestation:
    schema: str
    attestation_id: str
    issuer_id: str
    key_id: str
    provider_manifest_sha256: str
    adapter_id: str
    adapter_version: str
    adapter_source_sha256: str
    issued_at_epoch: int
    effective_epoch: int
    valid_until_epoch: int | None
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return provider_artifact_signature_payload(
            attestation_id=self.attestation_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            provider_manifest_sha256=self.provider_manifest_sha256,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            adapter_source_sha256=self.adapter_source_sha256,
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
class ReflexReplicationSnapshot:
    schema: str
    snapshot_id: str
    issuer_id: str
    key_id: str
    exported_at_epoch: int
    control_sha256: str
    root_anchor_sha256: str
    checkpoint_envelope_sha256: str | None
    signature_b64: str
    envelope_sha256: str

    def signing_payload(self) -> dict[str, object]:
        return replication_snapshot_signature_payload(
            snapshot_id=self.snapshot_id,
            issuer_id=self.issuer_id,
            key_id=self.key_id,
            exported_at_epoch=self.exported_at_epoch,
            control_sha256=self.control_sha256,
            root_anchor_sha256=self.root_anchor_sha256,
            checkpoint_envelope_sha256=self.checkpoint_envelope_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.signing_payload()
        payload["signature_b64"] = self.signature_b64
        payload["envelope_sha256"] = self.envelope_sha256
        return payload


class ReflexRootAttestationPlane:
    """v0.10 fail-closed wrapper over the v0.9 lifecycle plane."""

    def __init__(
        self,
        *,
        lifecycle: ReflexTrustLifecyclePlane | None = None,
        authority: ReflexAuthorityPlane | None = None,
        root: Path | None = None,
        root_pin: ReflexRootPin | None = None,
    ) -> None:
        if lifecycle is None:
            lifecycle = ReflexTrustLifecyclePlane(root=root, authority=authority)
        self.lifecycle = lifecycle
        self.authority = lifecycle.authority
        self.control = lifecycle.control
        self.root = self.control.root / "root-attestation"
        self._runtime_lock = self.control._runtime_lock
        self.root_pin = root_pin or root_pin_from_env()

    @property
    def artifact_attestations_dir(self) -> Path:
        return self.root / "provider-artifacts"

    @property
    def nonces_dir(self) -> Path:
        return self.root / "activation-nonces"

    @property
    def nonce_usage_dir(self) -> Path:
        return self.root / "nonce-usage"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "replication-snapshots"

    @runtime_locked
    def status(
        self,
        *,
        evaluation_epoch: int,
        adapter_id: str | None = None,
        adapter_version: str | None = None,
        adapter_source_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        pin_ok, pin_reason = self._root_pin_status()
        if not pin_ok:
            self._collapse_if_active(
                reason="external_root_pin_missing_or_mismatched",
                evaluation_epoch=epoch,
            )
        lifecycle_status = self.lifecycle.status(
            evaluation_epoch=epoch,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        artifact_ok: bool | None = None
        artifact_reason: str | None = None
        if (
            lifecycle_status.get("routing_influence_active") is True
            and adapter_id is not None
            and adapter_version is not None
            and adapter_source_sha256 is not None
        ):
            try:
                self._require_provider_artifact(
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                    adapter_source_sha256=adapter_source_sha256,
                    evaluation_epoch=epoch,
                )
                artifact_ok = True
            except ReflexRootAttestationContractError as exc:
                artifact_ok = False
                artifact_reason = str(exc)
                self._collapse_if_active(
                    reason="provider_artifact_attestation_invalid",
                    evaluation_epoch=epoch,
                )
                lifecycle_status = self.lifecycle.status(
                    evaluation_epoch=epoch,
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                )
        return {
            "ok": True,
            "evaluation_epoch": epoch,
            "root_pin": self.root_pin.to_dict() if self.root_pin else None,
            "root_pin_valid": pin_ok,
            "root_pin_reason": pin_reason,
            "provider_artifact_valid": artifact_ok,
            "provider_artifact_reason": artifact_reason,
            "routing_influence_active": lifecycle_status.get(
                "routing_influence_active", False
            ),
            "lifecycle": lifecycle_status,
            "provider_artifact_attestations": [
                item.to_dict() for item in self._list_provider_artifacts()
            ],
            "activation_nonces": [
                item.to_dict() for item in self._list_nonces()
            ],
            "nonce_usage": self._all_nonce_usage(),
            "replication_snapshots": [
                item.to_dict() for item in self._list_snapshots()
            ],
        }

    @runtime_locked
    def ingest_provider_artifact(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._require_root_pin()
        artifact = provider_artifact_from_payload(payload)
        _validate_provider_artifact(artifact)
        manifest = self._manifest_by_sha(artifact.provider_manifest_sha256)
        if manifest is None:
            raise ReflexRootAttestationContractError(
                "provider artifact targets unknown provider manifest"
            )
        if artifact.issuer_id != manifest.issuer_id:
            raise ReflexRootAttestationContractError(
                "provider artifact issuer must match provider manifest issuer"
            )
        if artifact.adapter_id != manifest.adapter_id:
            raise ReflexRootAttestationContractError(
                "provider artifact adapter_id differs from manifest"
            )
        if artifact.adapter_version != manifest.adapter_version:
            raise ReflexRootAttestationContractError(
                "provider artifact adapter_version differs from manifest"
            )
        self.lifecycle._require_live_signer(
            artifact.issuer_id,
            artifact.key_id,
            epoch,
        )
        self.authority.verify_signed_payload(
            issuer_id=artifact.issuer_id,
            key_id=artifact.key_id,
            purpose=PURPOSE_PROVIDER_ARTIFACT,
            payload=artifact.signing_payload(),
            signature_b64=artifact.signature_b64,
        )
        path = self.artifact_attestations_dir / (
            f"{_safe_id(artifact.attestation_id)}.json"
        )
        _idempotent_write(path, artifact.to_dict(), artifact.envelope_sha256)
        receipt = self._receipt(
            status="PROVIDER_ARTIFACT_INGESTED",
            reason="authenticated_adapter_source_digest_persisted",
            evaluation_epoch=epoch,
            related_sha=artifact.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="attestation",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {"ok": True, "artifact": artifact.to_dict(), "receipt": receipt}

    @runtime_locked
    def ingest_nonce(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._require_root_pin()
        nonce = activation_nonce_from_payload(payload)
        _validate_activation_nonce(nonce)
        envelope = self.authority.find_signed_grant_by_sha256(
            nonce.target_grant_sha256
        )
        if envelope is None:
            raise ReflexRootAttestationContractError(
                "activation nonce targets unknown authenticated grant"
            )
        if envelope.issuer_id != nonce.issuer_id:
            raise ReflexRootAttestationContractError(
                "activation nonce issuer must match grant issuer"
            )
        self.lifecycle._require_live_signer(
            nonce.issuer_id,
            nonce.key_id,
            epoch,
        )
        self.authority.verify_signed_payload(
            issuer_id=nonce.issuer_id,
            key_id=nonce.key_id,
            purpose=PURPOSE_ACTIVATION_NONCE,
            payload=nonce.signing_payload(),
            signature_b64=nonce.signature_b64,
        )
        path = self.nonces_dir / f"{_safe_id(nonce.nonce_id)}.json"
        _idempotent_write(path, nonce.to_dict(), nonce.envelope_sha256)
        return {"ok": True, "nonce": nonce.to_dict()}

    @runtime_locked
    def activate_verified(
        self,
        *,
        request: ReflexActivationRequest,
        grant_id: str,
        nonce_id: str,
        adapter_id: str,
        adapter_version: str,
        adapter_source_sha256: str,
        evaluation_epoch: int,
        lease_until_epoch: int | None = None,
        expected_control_sha256: str | None = None,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        self._require_root_pin()
        self._require_provider_artifact(
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            adapter_source_sha256=adapter_source_sha256,
            evaluation_epoch=epoch,
        )
        envelope = self.authority.find_signed_grant_by_id(grant_id)
        if envelope is None:
            raise ReflexRootAttestationContractError(
                "authenticated activation grant not found"
            )
        nonce = self._require_nonce(nonce_id)
        if nonce.target_grant_sha256 != envelope.grant.grant_sha256:
            raise ReflexRootAttestationContractError(
                "activation nonce grant scope mismatch"
            )
        if nonce.activation_request_sha256 != request.request_sha256:
            raise ReflexRootAttestationContractError(
                "activation nonce request scope mismatch"
            )
        if epoch < nonce.issued_at_epoch:
            raise ReflexRootAttestationContractError(
                "activation nonce is not valid yet"
            )
        if epoch >= nonce.valid_until_epoch:
            raise ReflexRootAttestationContractError(
                "activation nonce has expired"
            )
        if self._nonce_used(nonce.nonce_id):
            raise ReflexRootAttestationContractError(
                "activation nonce has already been consumed"
            )

        # Burn before delegating. A downstream failure can consume the nonce,
        # but a crash can never leave a successful activation with a reusable
        # nonce.
        self._consume_nonce(
            nonce,
            evaluation_epoch=epoch,
            activation_state_sha256=None,
            outcome="RESERVED",
        )
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
            self._consume_nonce(
                nonce,
                evaluation_epoch=epoch,
                activation_state_sha256=None,
                outcome="BURNED_ON_FAILURE",
                replace_existing=True,
            )
            raise

        activation = result.get("activation")
        activation_sha = (
            str(activation.get("state_sha256"))
            if isinstance(activation, dict)
            else None
        )
        self._consume_nonce(
            nonce,
            evaluation_epoch=epoch,
            activation_state_sha256=activation_sha,
            outcome="CONSUMED",
            replace_existing=True,
        )
        result["activation_nonce"] = {
            "nonce_id": nonce.nonce_id,
            "envelope_sha256": nonce.envelope_sha256,
            "consumed": True,
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
        adapter_source_sha256: str,
        evaluation_epoch: int,
    ) -> tuple[ReflexRoutingInfluenceSignal | None, dict[str, Any]]:
        epoch = _epoch(evaluation_epoch)
        try:
            self._require_root_pin()
            self._require_provider_artifact(
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                adapter_source_sha256=adapter_source_sha256,
                evaluation_epoch=epoch,
            )
        except ReflexRootAttestationContractError:
            collapse = self._collapse_if_active(
                reason="v0_10_root_or_provider_artifact_invalid",
                evaluation_epoch=epoch,
            )
            return None, collapse or {
                "status": "INACTIVE",
                "routing_influence_active": False,
            }
        return self.lifecycle.evaluate_active(
            reflex_input=reflex_input,
            baseline_provider=baseline_provider,
            influence_provider=influence_provider,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            evaluation_epoch=epoch,
        )

    @runtime_locked
    def export_checkpoint_bundle(
        self,
        *,
        checkpoint_id: str,
    ) -> dict[str, object]:
        checkpoint = self._checkpoint_by_id(checkpoint_id)
        anchor = self.authority.require_trust_anchor(
            issuer_id=checkpoint.issuer_id,
            key_id=checkpoint.key_id,
        )
        payload: dict[str, object] = {
            "schema": "phios.reflex_checkpoint_bundle.v0.10",
            "checkpoint": checkpoint.to_dict(),
            "trust_anchor": anchor.to_dict(),
        }
        payload["bundle_sha256"] = _digest(payload)
        return payload

    @runtime_locked
    def ingest_replication_snapshot(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_epoch: int,
    ) -> dict[str, Any]:
        epoch = _epoch(evaluation_epoch)
        pin = self._require_root_pin()
        snapshot = replication_snapshot_from_payload(payload)
        _validate_replication_snapshot(snapshot)
        if snapshot.root_anchor_sha256 != pin.anchor_sha256:
            raise ReflexRootAttestationContractError(
                "replication snapshot root pin differs from local root pin"
            )
        self.lifecycle._require_live_signer(
            snapshot.issuer_id,
            snapshot.key_id,
            epoch,
        )
        self.authority.verify_signed_payload(
            issuer_id=snapshot.issuer_id,
            key_id=snapshot.key_id,
            purpose=PURPOSE_REPLICATION_SNAPSHOT,
            payload=snapshot.signing_payload(),
            signature_b64=snapshot.signature_b64,
        )
        path = self.snapshots_dir / f"{_safe_id(snapshot.snapshot_id)}.json"
        _idempotent_write(path, snapshot.to_dict(), snapshot.envelope_sha256)

        local = self.authority.status(evaluation_epoch=epoch)
        aligned = snapshot.control_sha256 == local["control_sha256"]
        receipt = self._receipt(
            status="REPLICATION_ALIGNED" if aligned else "REPLICATION_CONFLICT",
            reason=(
                "remote_snapshot_matches_local_control"
                if aligned
                else "remote_snapshot_differs_no_authority_state_overwritten"
            ),
            evaluation_epoch=epoch,
            related_sha=snapshot.envelope_sha256,
        )
        self.control.append_audit_receipt(
            kind="replication",
            evaluation_epoch=epoch,
            receipt=receipt,
        )
        return {
            "ok": True,
            "aligned": aligned,
            "snapshot": snapshot.to_dict(),
            "local_control_sha256": local["control_sha256"],
            "receipt": receipt,
        }

    def _root_pin_status(self) -> tuple[bool, str]:
        if self.root_pin is None:
            return False, "PHIOS_REFLEX_ROOT_PIN is not configured"
        try:
            anchor = self.authority.require_trust_anchor(
                issuer_id=self.root_pin.issuer_id,
                key_id=self.root_pin.key_id,
            )
        except ReflexAuthorityContractError:
            return False, "pinned trust anchor is not present or valid"
        if anchor.anchor_sha256 != self.root_pin.anchor_sha256:
            return False, "pinned trust-anchor digest mismatch"
        return True, "exact external root pin matched"

    def _require_root_pin(self) -> ReflexRootPin:
        ok, reason = self._root_pin_status()
        if not ok or self.root_pin is None:
            raise ReflexRootAttestationContractError(reason)
        return self.root_pin

    def _require_provider_artifact(
        self,
        *,
        adapter_id: str,
        adapter_version: str,
        adapter_source_sha256: str,
        evaluation_epoch: int,
    ) -> ReflexProviderArtifactAttestation:
        _require_sha256(adapter_source_sha256, "adapter_source_sha256")
        manifests = self.lifecycle._list_manifests()
        active_manifest_shas = {
            item.envelope_sha256
            for item in manifests
            if item.adapter_id == adapter_id
            and item.adapter_version == adapter_version
            and item.effective_epoch <= evaluation_epoch
            and (
                item.valid_until_epoch is None
                or evaluation_epoch < item.valid_until_epoch
            )
        }
        for artifact in self._list_provider_artifacts():
            if artifact.provider_manifest_sha256 not in active_manifest_shas:
                continue
            if artifact.adapter_id != adapter_id:
                continue
            if artifact.adapter_version != adapter_version:
                continue
            if artifact.adapter_source_sha256 != adapter_source_sha256:
                continue
            if artifact.effective_epoch > evaluation_epoch:
                continue
            if (
                artifact.valid_until_epoch is not None
                and evaluation_epoch >= artifact.valid_until_epoch
            ):
                continue
            self.lifecycle._require_live_signer(
                artifact.issuer_id,
                artifact.key_id,
                evaluation_epoch,
            )
            self.authority.verify_signed_payload(
                issuer_id=artifact.issuer_id,
                key_id=artifact.key_id,
                purpose=PURPOSE_PROVIDER_ARTIFACT,
                payload=artifact.signing_payload(),
                signature_b64=artifact.signature_b64,
            )
            return artifact
        raise ReflexRootAttestationContractError(
            "no effective authenticated provider-artifact digest matches installed adapter"
        )

    def _manifest_by_sha(self, digest: str) -> ReflexProviderManifest | None:
        for manifest in self.lifecycle._list_manifests():
            if manifest.envelope_sha256 == digest:
                return manifest
        return None

    def _checkpoint_by_id(self, checkpoint_id: str) -> ReflexLedgerCheckpoint:
        normalized = _safe_id(checkpoint_id)
        for checkpoint in self.lifecycle._list_checkpoints():
            if checkpoint.checkpoint_id == normalized:
                return checkpoint
        raise ReflexRootAttestationContractError(
            "signed ledger checkpoint not found"
        )

    def _require_nonce(self, nonce_id: str) -> ReflexActivationNonce:
        path = self.nonces_dir / f"{_safe_id(nonce_id)}.json"
        if not path.exists():
            raise ReflexRootAttestationContractError(
                "activation nonce not found"
            )
        nonce = activation_nonce_from_payload(_read_object(path))
        _validate_activation_nonce(nonce)
        self.authority.verify_signed_payload(
            issuer_id=nonce.issuer_id,
            key_id=nonce.key_id,
            purpose=PURPOSE_ACTIVATION_NONCE,
            payload=nonce.signing_payload(),
            signature_b64=nonce.signature_b64,
        )
        return nonce

    def _nonce_used(self, nonce_id: str) -> bool:
        return (self.nonce_usage_dir / f"{_safe_id(nonce_id)}.json").exists()

    def _consume_nonce(
        self,
        nonce: ReflexActivationNonce,
        *,
        evaluation_epoch: int,
        activation_state_sha256: str | None,
        outcome: str,
        replace_existing: bool = False,
    ) -> None:
        path = self.nonce_usage_dir / f"{_safe_id(nonce.nonce_id)}.json"
        if path.exists() and not replace_existing:
            raise ReflexRootAttestationContractError(
                "activation nonce has already been consumed"
            )
        payload: dict[str, object] = {
            "schema": "phios.reflex_nonce_consumption.v0.10",
            "nonce_id": nonce.nonce_id,
            "nonce_envelope_sha256": nonce.envelope_sha256,
            "evaluation_epoch": evaluation_epoch,
            "activation_state_sha256": activation_state_sha256,
            "outcome": outcome,
        }
        payload["consumption_sha256"] = _digest(payload)
        _atomic_write_json(path, payload)

    def _all_nonce_usage(self) -> list[dict[str, Any]]:
        if not self.nonce_usage_dir.exists():
            return []
        return [
            _read_object(path)
            for path in sorted(self.nonce_usage_dir.glob("*.json"))
        ]

    def _collapse_if_active(
        self,
        *,
        reason: str,
        evaluation_epoch: int,
    ) -> dict[str, Any] | None:
        status = self.control.status(evaluation_epoch=evaluation_epoch)
        activation = status.get("activation")
        if (
            isinstance(activation, dict)
            and activation.get("routing_influence_active") is True
        ):
            return self.authority.deactivate(
                reason=reason,
                evaluation_epoch=evaluation_epoch,
            )
        return None

    def _list_provider_artifacts(
        self,
    ) -> list[ReflexProviderArtifactAttestation]:
        return _read_typed_dir(
            self.artifact_attestations_dir,
            provider_artifact_from_payload,
            _validate_provider_artifact,
        )

    def _list_nonces(self) -> list[ReflexActivationNonce]:
        return _read_typed_dir(
            self.nonces_dir,
            activation_nonce_from_payload,
            _validate_activation_nonce,
        )

    def _list_snapshots(self) -> list[ReflexReplicationSnapshot]:
        return _read_typed_dir(
            self.snapshots_dir,
            replication_snapshot_from_payload,
            _validate_replication_snapshot,
        )

    @staticmethod
    def _receipt(
        *,
        status: str,
        reason: str,
        evaluation_epoch: int,
        related_sha: str,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": "phios.reflex_root_attestation_receipt.v0.10",
            "status": status,
            "reason": reason,
            "evaluation_epoch": evaluation_epoch,
            "related_sha256": related_sha,
            "routing_influence_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        payload["receipt_sha256"] = _digest(payload)
        return payload


def root_pin_from_env() -> ReflexRootPin | None:
    """Parse PHIOS_REFLEX_ROOT_PIN as issuer:key_id:anchor_sha256."""

    raw = os.getenv("PHIOS_REFLEX_ROOT_PIN", "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 3:
        raise ReflexRootAttestationContractError(
            "PHIOS_REFLEX_ROOT_PIN must be issuer:key_id:anchor_sha256"
        )
    issuer_id, key_id, anchor_sha256 = parts
    _safe_id(issuer_id)
    _safe_id(key_id)
    _require_sha256(anchor_sha256, "anchor_sha256")
    return ReflexRootPin(
        issuer_id=issuer_id,
        key_id=key_id,
        anchor_sha256=anchor_sha256.lower(),
    )


def adapter_source_sha256(adapter_id: str) -> str:
    """Hash the installed Python source file for an adapter identifier."""

    module_name, sep, _qualname = adapter_id.partition(":")
    if not sep or not module_name.strip():
        raise ReflexRootAttestationContractError(
            "adapter_id must be module:qualname"
        )
    spec = importlib.util.find_spec(module_name)
    origin = spec.origin if spec is not None else None
    if not origin or origin in {"built-in", "frozen"}:
        raise ReflexRootAttestationContractError(
            "adapter source file cannot be resolved"
        )
    path = Path(origin)
    if not path.is_file():
        raise ReflexRootAttestationContractError(
            "adapter source path is not a regular file"
        )
    return _sha256_bytes(path.read_bytes())


def provider_artifact_signature_payload(
    *,
    attestation_id: str,
    issuer_id: str,
    key_id: str,
    provider_manifest_sha256: str,
    adapter_id: str,
    adapter_version: str,
    adapter_source_sha256: str,
    issued_at_epoch: int,
    effective_epoch: int,
    valid_until_epoch: int | None,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_provider_artifact.v0.10",
        "attestation_id": attestation_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "provider_manifest_sha256": provider_manifest_sha256,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "adapter_source_sha256": adapter_source_sha256,
        "issued_at_epoch": issued_at_epoch,
        "effective_epoch": effective_epoch,
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


def replication_snapshot_signature_payload(
    *,
    snapshot_id: str,
    issuer_id: str,
    key_id: str,
    exported_at_epoch: int,
    control_sha256: str,
    root_anchor_sha256: str,
    checkpoint_envelope_sha256: str | None,
) -> dict[str, object]:
    return {
        "schema": "phios.reflex_replication_snapshot.v0.10",
        "snapshot_id": snapshot_id,
        "issuer_id": issuer_id,
        "key_id": key_id,
        "exported_at_epoch": exported_at_epoch,
        "control_sha256": control_sha256,
        "root_anchor_sha256": root_anchor_sha256,
        "checkpoint_envelope_sha256": checkpoint_envelope_sha256,
    }


def build_provider_artifact(
    *,
    attestation_id: str,
    issuer_id: str,
    key_id: str,
    provider_manifest_sha256: str,
    adapter_id: str,
    adapter_version: str,
    adapter_source_sha256: str,
    issued_at_epoch: int,
    effective_epoch: int,
    valid_until_epoch: int | None,
    signature_b64: str,
) -> ReflexProviderArtifactAttestation:
    payload = provider_artifact_signature_payload(
        attestation_id=attestation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider_manifest_sha256=provider_manifest_sha256,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        adapter_source_sha256=adapter_source_sha256,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        valid_until_epoch=valid_until_epoch,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexProviderArtifactAttestation(
        schema=str(payload["schema"]),
        attestation_id=attestation_id,
        issuer_id=issuer_id,
        key_id=key_id,
        provider_manifest_sha256=provider_manifest_sha256,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        adapter_source_sha256=adapter_source_sha256,
        issued_at_epoch=issued_at_epoch,
        effective_epoch=effective_epoch,
        valid_until_epoch=valid_until_epoch,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_provider_artifact(result)
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
        schema=str(payload["schema"]),
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


def build_replication_snapshot(
    *,
    snapshot_id: str,
    issuer_id: str,
    key_id: str,
    exported_at_epoch: int,
    control_sha256: str,
    root_anchor_sha256: str,
    checkpoint_envelope_sha256: str | None,
    signature_b64: str,
) -> ReflexReplicationSnapshot:
    payload = replication_snapshot_signature_payload(
        snapshot_id=snapshot_id,
        issuer_id=issuer_id,
        key_id=key_id,
        exported_at_epoch=exported_at_epoch,
        control_sha256=control_sha256,
        root_anchor_sha256=root_anchor_sha256,
        checkpoint_envelope_sha256=checkpoint_envelope_sha256,
    )
    envelope = dict(payload)
    envelope["signature_b64"] = signature_b64
    result = ReflexReplicationSnapshot(
        schema=str(payload["schema"]),
        snapshot_id=snapshot_id,
        issuer_id=issuer_id,
        key_id=key_id,
        exported_at_epoch=exported_at_epoch,
        control_sha256=control_sha256,
        root_anchor_sha256=root_anchor_sha256,
        checkpoint_envelope_sha256=checkpoint_envelope_sha256,
        signature_b64=signature_b64,
        envelope_sha256=_digest(envelope),
    )
    _validate_replication_snapshot(result)
    return result


def provider_artifact_from_payload(
    payload: Mapping[str, Any],
) -> ReflexProviderArtifactAttestation:
    _require_schema(payload, "phios.reflex_provider_artifact.v0.10")
    valid_until = payload.get("valid_until_epoch")
    return ReflexProviderArtifactAttestation(
        schema=str(payload["schema"]),
        attestation_id=str(payload.get("attestation_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        provider_manifest_sha256=str(
            payload.get("provider_manifest_sha256", "")
        ),
        adapter_id=str(payload.get("adapter_id", "")),
        adapter_version=str(payload.get("adapter_version", "")),
        adapter_source_sha256=str(payload.get("adapter_source_sha256", "")),
        issued_at_epoch=_epoch_value(
            payload.get("issued_at_epoch"), "issued_at_epoch"
        ),
        effective_epoch=_epoch_value(
            payload.get("effective_epoch"), "effective_epoch"
        ),
        valid_until_epoch=(
            _epoch_value(valid_until, "valid_until_epoch")
            if valid_until is not None
            else None
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def activation_nonce_from_payload(
    payload: Mapping[str, Any],
) -> ReflexActivationNonce:
    _require_schema(payload, "phios.reflex_activation_nonce.v0.10")
    return ReflexActivationNonce(
        schema=str(payload["schema"]),
        nonce_id=str(payload.get("nonce_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        target_grant_sha256=str(payload.get("target_grant_sha256", "")),
        activation_request_sha256=str(
            payload.get("activation_request_sha256", "")
        ),
        issued_at_epoch=_epoch_value(
            payload.get("issued_at_epoch"), "issued_at_epoch"
        ),
        valid_until_epoch=_epoch_value(
            payload.get("valid_until_epoch"), "valid_until_epoch"
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def replication_snapshot_from_payload(
    payload: Mapping[str, Any],
) -> ReflexReplicationSnapshot:
    _require_schema(payload, "phios.reflex_replication_snapshot.v0.10")
    checkpoint = payload.get("checkpoint_envelope_sha256")
    return ReflexReplicationSnapshot(
        schema=str(payload["schema"]),
        snapshot_id=str(payload.get("snapshot_id", "")),
        issuer_id=str(payload.get("issuer_id", "")),
        key_id=str(payload.get("key_id", "")),
        exported_at_epoch=_epoch_value(
            payload.get("exported_at_epoch"), "exported_at_epoch"
        ),
        control_sha256=str(payload.get("control_sha256", "")),
        root_anchor_sha256=str(payload.get("root_anchor_sha256", "")),
        checkpoint_envelope_sha256=(
            str(checkpoint) if checkpoint is not None else None
        ),
        signature_b64=str(payload.get("signature_b64", "")),
        envelope_sha256=str(payload.get("envelope_sha256", "")),
    )


def verify_checkpoint_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a checkpoint bundle without any local PhiOS runtime state."""

    _require_schema(payload, "phios.reflex_checkpoint_bundle.v0.10")
    checkpoint_obj = payload.get("checkpoint")
    anchor_obj = payload.get("trust_anchor")
    if not isinstance(checkpoint_obj, dict) or not isinstance(anchor_obj, dict):
        raise ReflexRootAttestationContractError(
            "checkpoint bundle requires checkpoint and trust_anchor objects"
        )
    checkpoint = ledger_checkpoint_from_payload(checkpoint_obj)
    anchor = trust_anchor_from_payload(anchor_obj)
    _validate_trust_anchor(anchor)
    if checkpoint.issuer_id != anchor.issuer_id:
        raise ReflexRootAttestationContractError(
            "checkpoint issuer differs from bundled trust anchor"
        )
    if checkpoint.key_id != anchor.key_id:
        raise ReflexRootAttestationContractError(
            "checkpoint key differs from bundled trust anchor"
        )
    if PURPOSE_LEDGER_CHECKPOINT not in anchor.allowed_purposes:
        raise ReflexRootAttestationContractError(
            "bundled trust anchor cannot sign ledger checkpoints"
        )
    _verify_ed25519(
        anchor.public_key_b64,
        canonical_authority_bytes(checkpoint.signing_payload()),
        checkpoint.signature_b64,
    )
    expected = dict(payload)
    bundle_sha = str(expected.pop("bundle_sha256", ""))
    _require_sha256(bundle_sha, "bundle_sha256")
    if _digest(expected) != bundle_sha:
        raise ReflexRootAttestationContractError(
            "checkpoint bundle hash does not match contents"
        )
    return {
        "ok": True,
        "checkpoint_id": checkpoint.checkpoint_id,
        "issuer_id": checkpoint.issuer_id,
        "key_id": checkpoint.key_id,
        "ledger_entry_count": checkpoint.ledger_entry_count,
        "ledger_head_sha256": checkpoint.ledger_head_sha256,
        "control_sha256": checkpoint.control_sha256,
        "bundle_sha256": bundle_sha,
    }


def _validate_provider_artifact(
    item: ReflexProviderArtifactAttestation,
) -> None:
    if item.schema != "phios.reflex_provider_artifact.v0.10":
        raise ReflexRootAttestationContractError(
            "unsupported provider-artifact schema"
        )
    for value in (
        item.attestation_id,
        item.issuer_id,
        item.key_id,
        item.adapter_id,
        item.adapter_version,
    ):
        if not value.strip():
            raise ReflexRootAttestationContractError(
                "provider-artifact identifiers must be non-empty"
            )
    _require_sha256(
        item.provider_manifest_sha256, "provider_manifest_sha256"
    )
    _require_sha256(item.adapter_source_sha256, "adapter_source_sha256")
    if item.effective_epoch < item.issued_at_epoch:
        raise ReflexRootAttestationContractError(
            "provider artifact cannot be effective before issuance"
        )
    if (
        item.valid_until_epoch is not None
        and item.valid_until_epoch <= item.effective_epoch
    ):
        raise ReflexRootAttestationContractError(
            "provider artifact validity window is invalid"
        )
    _validate_envelope_hash(item.to_dict())


def _validate_activation_nonce(item: ReflexActivationNonce) -> None:
    if item.schema != "phios.reflex_activation_nonce.v0.10":
        raise ReflexRootAttestationContractError(
            "unsupported activation-nonce schema"
        )
    _safe_id(item.nonce_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    _require_sha256(item.target_grant_sha256, "target_grant_sha256")
    _require_sha256(
        item.activation_request_sha256, "activation_request_sha256"
    )
    if item.valid_until_epoch <= item.issued_at_epoch:
        raise ReflexRootAttestationContractError(
            "activation nonce validity window is invalid"
        )
    _validate_envelope_hash(item.to_dict())


def _validate_replication_snapshot(item: ReflexReplicationSnapshot) -> None:
    if item.schema != "phios.reflex_replication_snapshot.v0.10":
        raise ReflexRootAttestationContractError(
            "unsupported replication-snapshot schema"
        )
    _safe_id(item.snapshot_id)
    _safe_id(item.issuer_id)
    _safe_id(item.key_id)
    _require_sha256(item.control_sha256, "control_sha256")
    _require_sha256(item.root_anchor_sha256, "root_anchor_sha256")
    if item.checkpoint_envelope_sha256 is not None:
        _require_sha256(
            item.checkpoint_envelope_sha256,
            "checkpoint_envelope_sha256",
        )
    _validate_envelope_hash(item.to_dict())


def _read_typed_dir(path: Path, parser: Any, validator: Any) -> list[Any]:
    if not path.exists():
        return []
    result = []
    for item_path in sorted(path.glob("*.json")):
        item = parser(_read_object(item_path))
        validator(item)
        result.append(item)
    return result


def _idempotent_write(
    path: Path,
    payload: Mapping[str, object],
    envelope_sha256: str,
) -> None:
    if path.exists():
        existing = _read_object(path)
        if existing.get("envelope_sha256") != envelope_sha256:
            raise ReflexRootAttestationContractError(
                "artifact ID already exists with different contents"
            )
        return
    _atomic_write_json(path, payload)


def _require_schema(payload: Mapping[str, Any], schema: str) -> None:
    if payload.get("schema") != schema:
        raise ReflexRootAttestationContractError(
            f"unsupported schema; expected {schema}"
        )


def _epoch_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReflexRootAttestationContractError(
            f"{label} must be a non-negative integer"
        )
    return value


def _validate_envelope_hash(payload: dict[str, object]) -> None:
    expected = dict(payload)
    digest = str(expected.pop("envelope_sha256", ""))
    _require_sha256(digest, "envelope_sha256")
    if _digest(expected) != digest:
        raise ReflexRootAttestationContractError(
            "signed v0.10 envelope hash does not match contents"
        )


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()
