"""Project real build-sandbox receipts into the shared enforcement trust map."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.evidence_ref import EvidenceRef

from .control_plane_isolation import ControlPlaneIsolationReceipt
from .sandbox import BuildSandboxReceipt

SANDBOX_ENFORCEMENT_PROJECTION_SCHEMA_VERSION = (
    "phios.sandbox_enforcement_projection.v0.1"
)


class SandboxEnforcementProjectionError(ValueError):
    """Raised when sandbox receipts cannot support a truthful trust-map projection."""


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sandbox_evidence(receipt: BuildSandboxReceipt) -> EvidenceRef:
    return EvidenceRef.build(
        source_id="phios.apps.build-sandbox",
        source_kind="runtime-receipt",
        source_version=receipt.schema_version,
        content_sha256=receipt.sha256(),
        created_at=receipt.timestamp_utc,
        observed_at=receipt.timestamp_utc,
    )


def _control_plane_evidence(
    receipt: ControlPlaneIsolationReceipt,
) -> EvidenceRef:
    return EvidenceRef.build(
        source_id="phios.apps.control-plane-isolation",
        source_kind="runtime-receipt",
        source_version=receipt.schema_version,
        content_sha256=receipt.receipt_sha256,
        created_at=receipt.evaluated_at,
        observed_at=receipt.evaluated_at,
    )


def _filesystem_rule(
    receipt: BuildSandboxReceipt,
    evidence_sha256: str,
) -> EnforcementRule:
    controls = receipt.controls
    enforced = (
        controls.mount_namespace_enforced
        and controls.workspace_only_writable_mount
        and controls.host_system_roots_read_only
    )
    if enforced:
        return EnforcementRule.build(
            rule_id="build-workspace-write-confinement",
            effect_scope=("filesystem.change",),
            constraint=(
                "build filesystem writes remain confined to the reviewed "
                "writable workspace"
            ),
            layer="linux_namespaces",
            boundary="kernel_boundary",
            status="enforced",
            mechanism=(
                "mount namespace with workspace-only writable mount and "
                "read-only host system roots"
            ),
            evidence_ref_sha256s=(evidence_sha256,),
        )
    return EnforcementRule.build(
        rule_id="build-workspace-write-confinement",
        effect_scope=("filesystem.change",),
        constraint=(
            "build filesystem writes remain confined to the reviewed "
            "writable workspace"
        ),
        layer="unknown",
        boundary="unknown",
        status="unknown",
        mechanism="required mount-confinement evidence is incomplete",
        evidence_ref_sha256s=(evidence_sha256,),
    )


def _network_rule(
    receipt: BuildSandboxReceipt,
    evidence_sha256: str,
) -> EnforcementRule:
    controls = receipt.controls
    if (
        receipt.policy.network_mode == "deny"
        and controls.network_namespace_enforced
        and not controls.host_network_inherited
    ):
        return EnforcementRule.build(
            rule_id="build-network-request-boundary",
            effect_scope=("network.request",),
            constraint="build execution cannot reach the host network namespace",
            layer="linux_namespaces",
            boundary="kernel_boundary",
            status="enforced",
            mechanism="Bubblewrap network namespace isolation",
            evidence_ref_sha256s=(evidence_sha256,),
        )
    if receipt.policy.network_mode == "inherit" or controls.host_network_inherited:
        return EnforcementRule.build(
            rule_id="build-network-request-boundary",
            effect_scope=("network.request",),
            constraint="build execution cannot reach the host network namespace",
            layer="none",
            boundary="none",
            status="not_enforced",
            mechanism="host network namespace is inherited",
        )
    return EnforcementRule.build(
        rule_id="build-network-request-boundary",
        effect_scope=("network.request",),
        constraint="build execution cannot reach the host network namespace",
        layer="unknown",
        boundary="unknown",
        status="unknown",
        mechanism="network namespace enforcement is not established",
        evidence_ref_sha256s=(evidence_sha256,),
    )


def _control_plane_rule(
    receipt: ControlPlaneIsolationReceipt,
    evidence_sha256s: tuple[str, ...],
    effect_scope: tuple[str, ...],
) -> EnforcementRule:
    if (
        receipt.status == "ISOLATED"
        and not receipt.control_plane_reachable
        and not receipt.mutation_reachable
    ):
        return EnforcementRule.build(
            rule_id="build-control-plane-isolation",
            effect_scope=effect_scope,
            constraint=(
                "declared PhiOS control-plane surfaces remain unreachable "
                "from the build sandbox"
            ),
            layer="linux_namespaces",
            boundary="kernel_boundary",
            status="enforced",
            mechanism=(
                "sandbox namespace topology plus bounded path, environment, "
                "and loopback reachability evaluation"
            ),
            evidence_ref_sha256s=evidence_sha256s,
        )
    if receipt.status == "BLOCKED" or receipt.control_plane_reachable:
        return EnforcementRule.build(
            rule_id="build-control-plane-isolation",
            effect_scope=effect_scope,
            constraint=(
                "declared PhiOS control-plane surfaces remain unreachable "
                "from the build sandbox"
            ),
            layer="none",
            boundary="none",
            status="not_enforced",
            mechanism="declared control-plane surface is reachable",
        )
    return EnforcementRule.build(
        rule_id="build-control-plane-isolation",
        effect_scope=effect_scope,
        constraint=(
            "declared PhiOS control-plane surfaces remain unreachable "
            "from the build sandbox"
        ),
        layer="unknown",
        boundary="unknown",
        status="unknown",
        mechanism="control-plane isolation evidence is incomplete",
        evidence_ref_sha256s=evidence_sha256s,
    )


@dataclass(frozen=True, slots=True)
class SandboxEnforcementProjection:
    sandbox_evidence_ref: EvidenceRef
    control_plane_evidence_ref: EvidenceRef
    profile: EnforcementProfile
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = SANDBOX_ENFORCEMENT_PROJECTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sandbox_evidence_ref": self.sandbox_evidence_ref.to_dict(),
            "control_plane_evidence_ref": (
                self.control_plane_evidence_ref.to_dict()
            ),
            "profile": self.profile.to_dict(),
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


def project_build_sandbox_enforcement(
    *,
    intent: EffectIntent,
    sandbox: BuildSandboxReceipt,
    control_plane: ControlPlaneIsolationReceipt,
) -> SandboxEnforcementProjection:
    """Translate one real sandbox/control-plane receipt pair into a trust map."""

    if sandbox.control_plane_isolation_receipt_sha256 != control_plane.receipt_sha256:
        raise SandboxEnforcementProjectionError(
            "sandbox receipt does not bind the supplied control-plane receipt"
        )
    if _canonical_sha256(control_plane.body_dict()) != control_plane.receipt_sha256:
        raise SandboxEnforcementProjectionError(
            "control-plane receipt digest does not match canonical receipt body"
        )
    if control_plane.action_authority is not False:
        raise SandboxEnforcementProjectionError(
            "control-plane receipt cannot carry action authority"
        )
    if control_plane.execution_authority is not False:
        raise SandboxEnforcementProjectionError(
            "control-plane receipt cannot carry execution authority"
        )

    sandbox_evidence = _sandbox_evidence(sandbox)
    control_plane_evidence = _control_plane_evidence(control_plane)

    declared = set(intent.effects_declared)
    rules: list[EnforcementRule] = []

    if "filesystem.change" in declared:
        rules.append(
            _filesystem_rule(
                sandbox,
                sandbox_evidence.reference_sha256,
            )
        )

    if "network.request" in declared:
        rules.append(
            _network_rule(
                sandbox,
                sandbox_evidence.reference_sha256,
            )
        )

    control_scope = tuple(
        effect
        for effect in ("control_plane.change", "control_plane.read")
        if effect in declared
    )
    if control_scope:
        rules.append(
            _control_plane_rule(
                control_plane,
                tuple(
                    sorted(
                        {
                            sandbox_evidence.reference_sha256,
                            control_plane_evidence.reference_sha256,
                        }
                    )
                ),
                control_scope,
            )
        )

    profile = EnforcementProfile.build(
        intent=intent,
        rules=tuple(rules),
    )
    return SandboxEnforcementProjection(
        sandbox_evidence_ref=sandbox_evidence,
        control_plane_evidence_ref=control_plane_evidence,
        profile=profile,
    )
