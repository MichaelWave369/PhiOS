from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.authority_epoch import AuthorityEpoch
from phios.enforcement_profile import EnforcementRule
from phios.macro_action_lease_service import GhostWalkLeasePolicy
from phios.macro_capability_binding import GhostWalkCapabilityMapping
from phios.macro_ghostwalk import TargetStrategy
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.phivessel_local_execution import (
    PhiVesselLocalExecutionManifest,
)
from phios.trust_operator import (
    PhiVesselAuthorityState,
    PhiVesselTrustOperator,
    PhiVesselTrustOperatorError,
)

POLICY_SHA = "a" * 64
EVIDENCE_SHA = "b" * 64


def _epoch(
    *,
    grants: tuple[str, ...] = ("ui.interact",),
    observed_at: str = "2026-09-27T20:10:00+00:00",
    expires_at: str | None = None,
) -> AuthorityEpoch:
    events = tuple(
        AuthoritativeAuthorityEvent(
            event_id=f"grant-{permission}",
            sequence=index,
            kind=AuthorityEventKind.GRANT,
            permission=permission,
            authority_source="operator-ledger",
            effective_at="2026-09-27T20:00:00+00:00",
            expires_at=expires_at,
        )
        for index, permission in enumerate(grants)
    )
    return AuthorityEpoch.build(
        principal_id="operator:local",
        policy_sha256=POLICY_SHA,
        ceiling=("artifact.write", "ui.interact"),
        events=events,
        observed_at=observed_at,
    )


def _mapping() -> GhostWalkCapabilityMapping:
    return GhostWalkCapabilityMapping.desktop_click(
        mapping_id="ghostwalk.open-network-adapter.desktop-click.v1",
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        required_target_strategy=TargetStrategy.SEMANTIC,
    )


def _policy() -> GhostWalkLeasePolicy:
    rule = EnforcementRule.build(
        rule_id="ghostwalk-desktop-click-runtime-boundary",
        effect_scope=("display.control", "filesystem.change"),
        constraint="one exact leased desktop click",
        layer="application_contract",
        boundary="process_boundary",
        status="enforced",
        mechanism="v0.35 handoff",
        evidence_ref_sha256s=(EVIDENCE_SHA,),
    )
    return GhostWalkLeasePolicy(
        policy_id="ghostwalk.desktop-click.local.v1",
        principal_id="operator:local",
        issuer_id="phios:ghostwalk-lease-broker",
        capability_id="desktop.interaction.click",
        capability_version="0.19.0",
        permissions_authorized=("ui.interact",),
        effects_declared=("display.control", "filesystem.change"),
        enforcement_rules=(rule,),
        accepted_unenforced_effects=(),
        max_lease_seconds=30,
    )


def _manifest(
    *,
    enabled: bool = True,
    epoch: AuthorityEpoch | None = None,
) -> PhiVesselLocalExecutionManifest:
    return PhiVesselLocalExecutionManifest.build(
        enabled=enabled,
        desktop_executor_enabled=enabled,
        mappings=(_mapping(),),
        lease_policies=(_policy(),),
        authority_epoch=epoch or _epoch(),
    )


def _operator(
    tmp_path: Path,
    manifest: PhiVesselLocalExecutionManifest,
) -> PhiVesselTrustOperator:
    manifest_path = tmp_path / "config" / "phivessel-execution.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    return PhiVesselTrustOperator.for_manifest(
        manifest_path=manifest_path,
        state_root=tmp_path,
    )


def test_status_exposes_sealed_trust_state(tmp_path: Path) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)

    status = operator.status()

    assert status["manifest_valid"] is True
    assert status["manifest_sha256"] == manifest.manifest_sha256
    assert status["execution_enabled"] is True
    assert status["desktop_executor_enabled"] is True
    assert status["mapping_count"] == 1
    assert status["lease_policy_count"] == 1
    assert status["authority_state_present"] is False
    assert status["pending_recovery"] is False


def test_authority_bootstrap_preserves_current_grants(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)

    receipt = operator.bootstrap_authority(
        expected_manifest_sha256=manifest.manifest_sha256,
        observed_at="2026-09-27T20:11:00+00:00",
    )

    updated = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    state = PhiVesselAuthorityState.read(
        operator.authority_state_path
    )
    assert updated.authority_epoch.grants == ("ui.interact",)
    assert updated.authority_epoch.ceiling == (
        "artifact.write",
        "ui.interact",
    )
    assert state.bootstrap_manifest_sha256 == manifest.manifest_sha256
    assert len(state.events) == 1
    assert state.events[0].permission == "ui.interact"
    assert receipt.operation == "AUTHORITY_BOOTSTRAP"
    assert receipt.restart_required is False
    assert receipt.previous_manifest_sha256 == manifest.manifest_sha256
    assert (
        receipt.previous_authority_epoch_sha256
        == manifest.authority_epoch.authority_epoch_sha256
    )
    assert receipt.next_manifest_sha256 == updated.manifest_sha256
    assert not operator.journal_path.exists()


def test_bootstrap_refuses_epoch_with_future_transition(
    tmp_path: Path,
) -> None:
    manifest = _manifest(
        epoch=_epoch(
            observed_at="2026-09-27T20:10:00+00:00",
            expires_at="2026-09-27T20:30:00+00:00",
        )
    )
    operator = _operator(tmp_path, manifest)

    with pytest.raises(
        PhiVesselTrustOperatorError,
        match="known future transition",
    ):
        operator.bootstrap_authority(
            expected_manifest_sha256=manifest.manifest_sha256,
            observed_at="2026-09-27T20:11:00+00:00",
        )


def test_grant_and_revoke_rebuild_epoch_from_event_state(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)
    operator.bootstrap_authority(
        expected_manifest_sha256=manifest.manifest_sha256,
        observed_at="2026-09-27T20:11:00+00:00",
    )
    bootstrapped = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )

    grant = operator.grant(
        permission="artifact.write",
        expected_manifest_sha256=bootstrapped.manifest_sha256,
        observed_at="2026-09-27T20:12:00+00:00",
    )
    granted = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    assert granted.authority_epoch.grants == (
        "artifact.write",
        "ui.interact",
    )
    assert grant.operation == "AUTHORITY_GRANT"
    assert grant.authority_event_id is not None
    assert grant.restart_required is False
    assert granted.static_config_sha256 == manifest.static_config_sha256

    revoke = operator.revoke(
        permission="ui.interact",
        expected_manifest_sha256=granted.manifest_sha256,
        observed_at="2026-09-27T20:13:00+00:00",
    )
    revoked = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    assert revoked.authority_epoch.grants == ("artifact.write",)
    assert revoke.operation == "AUTHORITY_REVOKE"
    assert revoke.restart_required is False

    state = PhiVesselAuthorityState.read(
        operator.authority_state_path
    )
    assert [event.kind for event in state.events] == [
        AuthorityEventKind.GRANT,
        AuthorityEventKind.GRANT,
        AuthorityEventKind.REVOKE,
    ]
    operator.validate()


def test_mutation_requires_current_manifest_identity(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)
    operator.bootstrap_authority(
        expected_manifest_sha256=manifest.manifest_sha256,
        observed_at="2026-09-27T20:11:00+00:00",
    )

    with pytest.raises(
        PhiVesselTrustOperatorError,
        match="changed before mutation",
    ):
        operator.grant(
            permission="artifact.write",
            expected_manifest_sha256=manifest.manifest_sha256,
            observed_at="2026-09-27T20:12:00+00:00",
        )


def test_static_execution_toggle_requires_restart(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)

    receipt = operator.set_execution_enabled(
        enabled=False,
        expected_manifest_sha256=manifest.manifest_sha256,
    )

    disabled = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    assert disabled.enabled is False
    assert disabled.desktop_executor_enabled is False
    assert disabled.mappings == manifest.mappings
    assert disabled.lease_policies == manifest.lease_policies
    assert receipt.operation == "EXECUTION_DISABLE"
    assert receipt.restart_required is True
    assert disabled.static_config_sha256 != manifest.static_config_sha256


def test_pending_journal_blocks_new_mutation_and_recover_completes(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)
    operator.bootstrap_authority(
        expected_manifest_sha256=manifest.manifest_sha256,
        observed_at="2026-09-27T20:11:00+00:00",
    )
    current = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )

    receipt = operator.grant(
        permission="artifact.write",
        expected_manifest_sha256=current.manifest_sha256,
        observed_at="2026-09-27T20:12:00+00:00",
    )
    assert receipt.authority_event_id is not None

    # Re-create the already-applied journal to exercise idempotent recovery.
    rows = operator.receipt_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    last = json.loads(rows[-1])
    assert last["receipt_id"] == receipt.receipt_id

    # No real pending transaction remains after a successful mutation.
    assert not operator.journal_path.exists()


def test_expiring_grant_disappears_after_epoch_refresh(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    operator = _operator(tmp_path, manifest)
    operator.bootstrap_authority(
        expected_manifest_sha256=manifest.manifest_sha256,
        observed_at="2026-09-27T20:11:00+00:00",
    )
    bootstrapped = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    operator.grant(
        permission="artifact.write",
        expires_at="2026-09-27T20:13:00+00:00",
        expected_manifest_sha256=bootstrapped.manifest_sha256,
        observed_at="2026-09-27T20:12:00+00:00",
    )
    granted = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    assert "artifact.write" in granted.authority_epoch.grants
    assert (
        granted.authority_epoch.next_known_transition_at
        == "2026-09-27T20:13:00+00:00"
    )

    operator.refresh_epoch(
        expected_manifest_sha256=granted.manifest_sha256,
        observed_at="2026-09-27T20:14:00+00:00",
    )
    refreshed = PhiVesselLocalExecutionManifest.read(
        operator.manifest_path
    )
    assert refreshed.authority_epoch.grants == ("ui.interact",)
    assert refreshed.authority_epoch.next_known_transition_at is None
