"""Explicit terminal review of the existing decision -> binding -> lease chain.

This process never installs or calls an executor. A terminal is an intentional
operator interface, not proof of a human or isolation from a malicious process
running as the same OS user. Such processes must use a separate OS principal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from phios.macro_accepted_intent import GhostWalkAcceptedIntentRegistry
from phios.macro_action_lease_service import GhostWalkActionLeaseService, GhostWalkLeasePolicyRegistry
from phios.macro_authority_request import GhostWalkAuthorityRequestService
from phios.macro_authorization_console import (
    GhostWalkAuthorizationConsoleError,
    GhostWalkAuthorizationConsoleService,
    GhostWalkAuthorizationConsoleSnapshot,
)
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationDecisionService,
)
from phios.macro_capability_binding import (
    GhostWalkCapabilityBindingService,
    GhostWalkCapabilityMappingRegistry,
)
from phios.macro_ghostwalk_control_server import DEFAULT_OPERATOR_AUTHOR_ID, default_state_root
from phios.macro_ghostwalk_operator_editor import GhostWalkOperatorEditor
from phios.macro_policy_admission import GhostWalkPolicyAdmissionService, GhostWalkPolicyProfile
from phios.phivessel_local_execution import (
    ManifestAuthorityEpochProvider,
    PhiVesselLocalExecutionManifest,
    execution_manifest_path,
)
from phios.spine.ledger import RealityLedger


def _check_owned_path(path: Path) -> None:
    """Reject symlinks and shared-writable state before constructing services."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"operator state must not be a symlink: {path}")
    if os.name == "posix":
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError(f"operator state must be owned by you and not shared-writable: {path}")


def build_operator_console(state_root: Path) -> GhostWalkAuthorizationConsoleService:
    root = state_root.expanduser().absolute()
    # Existing state is never silently repaired or permission-changed.
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _check_owned_path(root)
    for path in root.rglob("*"):
        _check_owned_path(path)
    ledger_dir = root / "ledger"
    ledger_dir.mkdir(exist_ok=True, mode=0o700)
    ledger = RealityLedger(ledger_dir / "receipts.jsonl")
    editor = GhostWalkOperatorEditor(ledger=ledger, author_id=DEFAULT_OPERATOR_AUTHOR_ID)
    intents = GhostWalkAcceptedIntentRegistry(ledger=ledger, accepted_by=DEFAULT_OPERATOR_AUTHOR_ID)
    admission = GhostWalkPolicyAdmissionService(
        ledger=ledger, accepted_intents=intents, operator_editor=editor,
        profile=GhostWalkPolicyProfile.from_environment(os.environ),
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger, policy_admission=admission, requester_id=DEFAULT_OPERATOR_AUTHOR_ID,
    )
    decisions = GhostWalkAuthorizationDecisionService(
        ledger=ledger, authority_requests=requests, authorizer_id=DEFAULT_OPERATOR_AUTHOR_ID,
    )
    manifest_path = execution_manifest_path(state_root=root)
    if not manifest_path.absolute().is_relative_to(root):
        raise ValueError("operator execution manifest must be inside the protected state root")
    if not manifest_path.exists():
        return GhostWalkAuthorizationConsoleService(authorization_decisions=decisions)
    _check_owned_path(manifest_path)
    manifest = PhiVesselLocalExecutionManifest.read(manifest_path)
    if not manifest.enabled:
        return GhostWalkAuthorizationConsoleService(authorization_decisions=decisions)
    # The installed desktop executor currently only supports Windows. Linux
    # previews must not mint a lease for an unavailable effect implementation.
    if sys.platform != "win32" or not manifest.desktop_executor_enabled:
        raise ValueError("desktop binding and lease issuance require the supported Windows host")
    bindings = GhostWalkCapabilityBindingService(
        ledger=ledger, authorization_decisions=decisions,
        registry=GhostWalkCapabilityMappingRegistry(manifest.mappings),
    )
    leases = GhostWalkActionLeaseService(
        ledger=ledger, capability_bindings=bindings,
        policies=GhostWalkLeasePolicyRegistry(manifest.lease_policies),
        authority_epochs=ManifestAuthorityEpochProvider(
            path=manifest_path, expected_static_config_sha256=manifest.static_config_sha256,
        ),
    )
    return GhostWalkAuthorizationConsoleService(
        authorization_decisions=decisions, capability_bindings=bindings, action_leases=leases,
    )


def _perform(
    console: GhostWalkAuthorizationConsoleService,
    snapshot: GhostWalkAuthorizationConsoleSnapshot,
    action: str,
    decision: str | None,
    note: str | None,
) -> dict[str, object]:
    target = snapshot.target_inference_receipt_sha256
    if action == "decide":
        auth = snapshot.authorization_readiness
        if not auth.ready or auth.authority_request_sha256 is None or decision is None:
            raise ValueError(f"decision held: {auth.reason.value}")
        return console.record_decision(
            target_inference_receipt_sha256=target,
            expected_authority_request_sha256=auth.authority_request_sha256,
            expected_previous_decision_sha256=auth.latest_decision_sha256,
            decision=GhostWalkAuthorizationDecisionKind(decision), decision_note=note,
        ).to_dict()
    if action == "bind":
        binding = snapshot.binding_readiness
        if (binding is None or not binding.ready or binding.authorization_decision_sha256 is None
                or binding.selected_mapping_sha256 is None):
            raise ValueError("binding held: current trusted mapping and approval required")
        return console.create_binding(
            target_inference_receipt_sha256=target,
            expected_authorization_decision_sha256=binding.authorization_decision_sha256,
            expected_mapping_sha256=binding.selected_mapping_sha256,
            expected_mapping_set_sha256=binding.mapping_set_sha256,
            bound_at=datetime.now(UTC).isoformat(),
        ).to_dict()
    lease = snapshot.lease_readiness
    if (lease is None or not lease.ready or lease.executable_binding_sha256 is None
            or lease.policy_sha256 is None or lease.enforcement_profile_sha256 is None
            or lease.authority_epoch_sha256 is None):
        raise ValueError("lease held: current binding, policy, enforcement and authority required")
    return console.issue_lease(
        target_inference_receipt_sha256=target,
        expected_executable_binding_sha256=lease.executable_binding_sha256,
        expected_policy_sha256=lease.policy_sha256,
        expected_policy_set_sha256=lease.policy_set_sha256,
        expected_enforcement_profile_sha256=lease.enforcement_profile_sha256,
        expected_authority_epoch_sha256=lease.authority_epoch_sha256,
    ).to_dict()


def review(
    console: GhostWalkAuthorizationConsoleService, *, target: str, action: str,
    decision: str | None = None, note: str | None = None,
    input_stream: TextIO, output_stream: TextIO,
) -> int:
    if action not in {"inspect", "decide", "bind", "lease"}:
        raise ValueError("unsupported operator action")
    if action != "inspect" and not (input_stream.isatty() and output_stream.isatty()):
        raise ValueError("operator mutations require an interactive terminal; no unattended flag exists")
    snapshot = console.snapshot(target_inference_receipt_sha256=target)
    # JSON escaping prevents proposal text from injecting terminal control codes.
    print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=True), file=output_stream)
    if action == "inspect":
        return 0
    confirmation = f"{decision if action == 'decide' else action.upper()} {snapshot.snapshot_sha256}"
    print(f"Type exactly {confirmation} to confirm, or anything else to cancel:",
          file=output_stream, flush=True)
    if input_stream.readline().strip() != confirmation:
        print("Cancelled; no decision, binding, or lease was created.", file=output_stream)
        return 2
    current = console.snapshot(target_inference_receipt_sha256=target)
    if current.snapshot_sha256 != snapshot.snapshot_sha256:
        raise ValueError("evidence changed during review; inspect and confirm again")
    result = _perform(console, snapshot, action, decision, note)
    print(json.dumps({"operator_action": action, "result": result,
                      "execution_authority": False, "effect_performed": False}, indent=2),
          file=output_stream)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--target", required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("inspect")
    decide = actions.add_parser("decide")
    decide.add_argument("decision", choices=("APPROVE", "HOLD", "DENY"))
    decide.add_argument("--note")
    actions.add_parser("bind")
    actions.add_parser("lease")
    args = parser.parse_args(argv)
    try:
        if re.fullmatch(r"[0-9a-f]{64}", args.target) is None:
            raise ValueError("target must be a lowercase SHA-256 digest")
        if args.action != "inspect" and not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise ValueError("operator mutations require an interactive terminal")
        return review(build_operator_console(args.state_root), target=args.target, action=args.action,
                      decision=getattr(args, "decision", None), note=getattr(args, "note", None),
                      input_stream=sys.stdin, output_stream=sys.stdout)
    except (ValueError, OSError, GhostWalkAuthorizationConsoleError) as exc:
        print(f"Operator action held: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
