from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from phios.authority_epoch import AuthorityEpoch, AuthorityEpochContractError
from phios.enforcement_profile import EnforcementRule
from phios.macro_action_lease_service import GhostWalkLeasePolicy
from phios.macro_authority_request import GhostWalkAuthorityRequestService
from phios.macro_capability_binding import GhostWalkCapabilityMapping
from phios.macro_desktop_interaction import GovernedDesktopClickExecutor
from phios.macro_ghostwalk import TargetStrategy
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.phivessel_local_execution import (
    ManifestAuthorityEpochProvider,
    PhiVesselLocalExecutionError,
    PhiVesselLocalExecutionManifest,
    build_local_execution_mount,
    execution_manifest_path,
)
from phios.spine.executor import ArtifactResult
from phios.spine.ledger import RealityLedger
from phios.spine.runtime import PhiOSSpine

POLICY_SHA = "a" * 64


def _epoch(
    *,
    observed_at: str = "2026-09-27T20:10:00+00:00",
    expires_at: str = "2026-09-27T20:30:00+00:00",
) -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256=POLICY_SHA,
        ceiling=("ui.interact",),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-ui-interact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="ui.interact",
                authority_source="operator-ledger",
                effective_at="2026-09-27T20:00:00+00:00",
                expires_at=expires_at,
            ),
        ),
        observed_at=observed_at,
    )


def _mapping(
    *,
    mapping_id: str = "ghostwalk.open-network-adapter.desktop-click.v1",
) -> GhostWalkCapabilityMapping:
    return GhostWalkCapabilityMapping.desktop_click(
        mapping_id=mapping_id,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        required_target_strategy=TargetStrategy.SEMANTIC,
    )


def _rule() -> EnforcementRule:
    return EnforcementRule.build(
        rule_id="ghostwalk-desktop-click-runtime-boundary",
        effect_scope=("display.control", "filesystem.change"),
        constraint="one exact leased desktop click enters the governed executor",
        layer="application_contract",
        boundary="process_boundary",
        status="enforced",
        mechanism="PhiVessel local execution manifest + v0.35 handoff",
    )


def _policy(
    *,
    policy_id: str = "ghostwalk.desktop-click.local.v1",
) -> GhostWalkLeasePolicy:
    return GhostWalkLeasePolicy(
        policy_id=policy_id,
        principal_id="operator:local",
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        permissions_authorized=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        enforcement_rules=(_rule(),),
        accepted_unenforced_effects=(),
        max_lease_seconds=30,
    )


def _manifest(
    *,
    enabled: bool = True,
    mapping: GhostWalkCapabilityMapping | None = None,
    policy: GhostWalkLeasePolicy | None = None,
    epoch: AuthorityEpoch | None = None,
) -> PhiVesselLocalExecutionManifest:
    return PhiVesselLocalExecutionManifest.build(
        enabled=enabled,
        desktop_executor_enabled=enabled,
        mappings=((mapping or _mapping()),) if enabled else (),
        lease_policies=((policy or _policy()),) if enabled else (),
        authority_epoch=epoch or _epoch(),
    )


def _write(
    path: Path,
    manifest: PhiVesselLocalExecutionManifest,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), sort_keys=True),
        encoding="utf-8",
    )


class _FakeDesktopExecutor:
    def execute(self, _payload: dict[str, object]) -> ArtifactResult:
        raise AssertionError("mount test must not execute desktop effect")


def _fake_factory(
    _spine: PhiOSSpine,
) -> GovernedDesktopClickExecutor:
    return cast(
        GovernedDesktopClickExecutor,
        _FakeDesktopExecutor(),
    )


def _authority_requests() -> GhostWalkAuthorityRequestService:
    return cast(GhostWalkAuthorityRequestService, object())


def test_default_manifest_path_is_under_state_root(tmp_path: Path) -> None:
    assert execution_manifest_path(
        state_root=tmp_path,
        environ={},
    ) == tmp_path / "config" / "phivessel-execution.json"


def test_environment_can_override_manifest_path(tmp_path: Path) -> None:
    configured = tmp_path / "trusted" / "execution.json"
    assert execution_manifest_path(
        state_root=tmp_path,
        environ={
            "PHIOS_PHIVESSEL_EXECUTION_MANIFEST": str(configured)
        },
    ) == configured


def test_absent_manifest_leaves_execution_unmounted(tmp_path: Path) -> None:
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")

    mount = build_local_execution_mount(
        state_root=tmp_path,
        ledger=ledger,
        authority_requests=_authority_requests(),
        authorizer_id="operator:local",
        manifest_path=tmp_path / "missing.json",
        desktop_executor_factory=_fake_factory,
    )

    assert mount is None


def test_disabled_manifest_leaves_execution_unmounted(tmp_path: Path) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    _write(path, _manifest(enabled=False))
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")

    mount = build_local_execution_mount(
        state_root=tmp_path,
        ledger=ledger,
        authority_requests=_authority_requests(),
        authorizer_id="operator:local",
        manifest_path=path,
        desktop_executor_factory=_fake_factory,
    )

    assert mount is None


def test_valid_manifest_mounts_real_v035_handoff(tmp_path: Path) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    manifest = _manifest()
    _write(path, manifest)
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")

    mount = build_local_execution_mount(
        state_root=tmp_path,
        ledger=ledger,
        authority_requests=_authority_requests(),
        authorizer_id="operator:local",
        manifest_path=path,
        desktop_executor_factory=_fake_factory,
    )

    assert mount is not None
    assert mount.manifest_sha256 == manifest.manifest_sha256
    capability = mount.spine.registry.get("desktop.interaction.click")
    assert capability.version == "0.19.0"
    assert tuple(capability.permissions) == ("ui.interact",)
    assert mount.authority_epochs.current() == manifest.authority_epoch
    assert mount.execution_handoff is not None
    assert mount.action_leases is not None


def test_authority_only_change_is_reloaded_without_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    original = _manifest()
    _write(path, original)
    provider = ManifestAuthorityEpochProvider(
        path=path,
        expected_static_config_sha256=(
            original.static_config_sha256
        ),
    )
    changed = _manifest(
        epoch=_epoch(
            observed_at="2026-09-27T20:11:00+00:00",
            expires_at="2026-09-27T20:31:00+00:00",
        )
    )
    _write(path, changed)

    current = provider.current()

    assert current is not None
    assert current.authority_epoch_sha256 == (
        changed.authority_epoch.authority_epoch_sha256
    )
    assert current.authority_epoch_sha256 != (
        original.authority_epoch.authority_epoch_sha256
    )


def test_mapping_change_requires_restart(tmp_path: Path) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    original = _manifest()
    _write(path, original)
    provider = ManifestAuthorityEpochProvider(
        path=path,
        expected_static_config_sha256=(
            original.static_config_sha256
        ),
    )
    changed = _manifest(
        mapping=_mapping(
            mapping_id="ghostwalk.open-network-adapter.desktop-click.v2"
        )
    )
    _write(path, changed)

    with pytest.raises(
        AuthorityEpochContractError,
        match="restart is required",
    ):
        provider.current()


def test_policy_change_requires_restart(tmp_path: Path) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    original = _manifest()
    _write(path, original)
    provider = ManifestAuthorityEpochProvider(
        path=path,
        expected_static_config_sha256=(
            original.static_config_sha256
        ),
    )
    changed = _manifest(
        policy=_policy(
            policy_id="ghostwalk.desktop-click.local.v2"
        )
    )
    _write(path, changed)

    with pytest.raises(
        AuthorityEpochContractError,
        match="restart is required",
    ):
        provider.current()


def test_tampered_manifest_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config" / "phivessel-execution.json"
    manifest = _manifest()
    payload = manifest.to_dict()
    payload["enabled"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        PhiVesselLocalExecutionError,
        match="SHA-256 mismatch",
    ):
        PhiVesselLocalExecutionManifest.read(path)


def test_policy_permission_cannot_exceed_authority_ceiling() -> None:
    epoch = AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256=POLICY_SHA,
        ceiling=("artifact.write",),
        events=(),
        observed_at="2026-09-27T20:10:00+00:00",
    )

    with pytest.raises(
        PhiVesselLocalExecutionError,
        match="exceeds AuthorityEpoch ceiling",
    ):
        _manifest(epoch=epoch)
