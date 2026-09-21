# PhiOS App Platform v0.50 — Release Install Proposal Gate

## Status

Alpha contract.

New schema:

- phios.release_install_proposal.v0.1

Current install receipt schema:

- phios.app_install_receipt.v0.2

Compatibility reader retained:

- phios.app_install_receipt.v0.1

## Purpose

v0.49 proves which reviewed release chain produced a package.

v0.50 governs the next transition: proposing that exact release package for a bounded side-by-side candidate install.

The central rule is:

> Provenance can support a proposal. Provenance is not install or update authority.

## Proposal creation

The operator supplies:

1. one exact v0.49 BuildPackagePlan;
2. the exact approved package-plan SHA-256.

Proposal creation fails unless the package plan carries a non-null v0.48 release-build review digest.

Ordinary package plans cannot mint a release install proposal.

A successful proposal binds:

- package_plan_sha256;
- release_build_review_sha256;
- app_id;
- app_version;
- repository_url;
- commit_sha;
- manifest_sha256;
- registry_snapshot_sha256;
- execution_receipt_sha256;
- offline_build_receipt_sha256;
- artifact_set_sha256;
- install_relative_path.

Every proposal fixes:

    proposal_state = proposed_for_side_by_side_install_review
    proposal_scope = release_candidate_install_only
    compatibility_verdict = not_assessed
    install_authority = false
    launch_authority = false
    update_authority = false
    rollback_authority = false

The proposal has its own canonical SHA-256.

## Proposal meaning

The record means only:

    A human selected this exact lineage-bound release package
    for consideration as a side-by-side installed candidate.

It does not mean:

    the release is compatible
    installation is authorized merely because the proposal exists
    the candidate may launch
    the candidate may replace the active version
    update is authorized
    rollback is authorized

## Install enforcement

AppInstallService remains the bounded artifact-install executor.

For a package whose release_build_review_sha256 is non-null, installation now requires:

- the exact approved package-plan SHA-256;
- one exact v0.50 release install proposal;
- the exact approved proposal SHA-256.

The proposal is strictly reconstructed and revalidated against the current package plan.

Installation is rejected unless the proposal still matches the plan's:

- canonical digest;
- release-build review lineage;
- app and version;
- repository and exact commit;
- manifest and registry snapshot;
- execution and offline-build receipts;
- artifact-set digest;
- install-relative path.

A proposal for another package cannot be reused.

## Ordinary packages

A package without release lineage keeps the existing install path.

Supplying release-install proposal inputs to an ordinary package fails closed.

This prevents proposal records from becoming generic install authority tokens.

## Install receipt lineage

Current AppInstallReceipt uses:

    phios.app_install_receipt.v0.2

It carries:

    release_install_proposal_sha256=<exact proposal digest or null>

For a release install, the exact approved proposal digest is written into the receipt.

For an ordinary install, the value is null.

The field participates in the canonical install-receipt SHA-256.

This gives later update planning a direct proof that the candidate install passed the v0.50 proposal gate.

## Legacy compatibility

Legacy phios.app_install_receipt.v0.1 remains strictly reconstructible.

A v0.1 receipt:

- has no release_install_proposal_sha256 field;
- reconstructs only with the historical field set;
- cannot carry or invent v0.50 lineage.

## Existing install authority remains separate

v0.50 does not replace the existing package-plan approval.

The install action still requires:

    approved_package_plan_sha256 == canonical package plan SHA-256

The v0.50 proposal approval is an additional release-specific prerequisite.

Therefore:

    proposal created
    != install authorized

    proposal approved
    without exact package-plan approval
    != install authorized

    install completed
    != launch authorized

    candidate installed
    != update authorized

## CLI

Create the proposal:

    phi-app propose-release-install \
      package-plan.json \
      --approve-package-plan-sha EXACT_PACKAGE_PLAN_SHA

Install the exact proposed release candidate:

    phi-app install-package \
      package-plan.json \
      registry.json \
      build-execution-receipt.json \
      offline-build-receipt.json \
      --approve-package-plan-sha EXACT_PACKAGE_PLAN_SHA \
      --release-install-proposal-json release-install-proposal.json \
      --approve-release-install-proposal-sha EXACT_PROPOSAL_SHA

## Fail-closed behavior

v0.50 rejects:

- stale package-plan approval during proposal creation;
- proposal creation from an ordinary package;
- malformed proposal records;
- proposal authority fields set true;
- release install without a v0.50 proposal;
- stale proposal approval;
- proposal bound to another package plan;
- release lineage mismatch between build evidence and package plan;
- release proposal inputs supplied to an ordinary package;
- malformed v0.2 install proposal digest;
- proposal lineage inserted into a legacy v0.1 install receipt.

## Tests

v0.50 tests cover:

- exact package-plan proposal binding;
- fixed zero-authority proposal semantics;
- strict proposal round trip;
- stale package-plan approval rejection;
- ordinary package proposal rejection;
- tampered proposal rejection;
- release install blocked without proposal;
- exact proposal allowing bounded side-by-side install;
- exact proposal digest written into the install receipt;
- stale proposal approval rejection;
- cross-package proposal rejection;
- ordinary install compatibility;
- ordinary install rejection of irrelevant proposal inputs;
- legacy v0.1 install-receipt round trip.

## Next boundary

The next rung should bind the v0.50 proposal-bearing candidate install receipt into the actual desktop update plan.

That future gate should establish:

    this exact installed candidate
    came from this exact reviewed release chain

without changing the existing rule:

    installed candidate
    != permission to replace the active desktop version
