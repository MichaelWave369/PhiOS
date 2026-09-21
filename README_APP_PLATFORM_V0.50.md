# PhiOS App Platform v0.50

**Release provenance can justify a proposal. It still cannot install or update anything by itself.**

v0.50 adds a governed release-install proposal gate between the v0.49 lineage-bound package plan and side-by-side candidate installation.

The release chain is now:

    v0.44 release candidate
        ↓
    v0.45 structural evidence
        ↓
    v0.46 human acceptance
        ↓
    v0.47 candidate advancement
        ↓
    gated BuildPlan
        ↓
    v0.48 release build review
        ↓
    reviewed execution request
        ↓
    v0.49 lineage-bound execution receipt
        ↓
    lineage-bound package plan
        ↓
    v0.50 release install proposal
        ↓
    exact proposal approval + exact package-plan approval
        ↓
    side-by-side candidate install receipt
        ↓
    launch authority = false
    update authority = not granted

The central rule is:

    PROVENANCE != INSTALL AUTHORITY
    INSTALL != UPDATE AUTHORITY

## Release install proposal

A release-lineage package may be proposed with:

    phi-app propose-release-install \
      package-plan.json \
      --approve-package-plan-sha EXACT_PACKAGE_PLAN_SHA

The proposal binds the exact:

- package-plan SHA-256;
- v0.48 release-build review SHA-256 carried by v0.49;
- app ID and version;
- repository and exact commit;
- manifest and registry snapshot;
- build execution receipt;
- offline build receipt;
- artifact-set digest;
- install-relative path.

Every proposal fixes:

    proposal_state = proposed_for_side_by_side_install_review
    proposal_scope = release_candidate_install_only
    compatibility_verdict = not_assessed
    install_authority = false
    launch_authority = false
    update_authority = false
    rollback_authority = false

## Install gate

Release-lineage packages now require both:

1. the existing exact package-plan approval; and
2. the exact v0.50 proposal plus exact proposal approval.

Ordinary non-release package installs retain the existing behavior and reject irrelevant release-proposal inputs.

## Install receipt lineage

Current install receipts use:

    phios.app_install_receipt.v0.2

For a release candidate they carry:

    release_install_proposal_sha256=<exact v0.50 digest>

That digest participates in the canonical install receipt SHA-256.

Ordinary installs carry an explicit null proposal lineage value.

Legacy v0.1 install receipts remain readable and cannot invent release proposal lineage.

## What v0.50 does not do

v0.50 does not:

- assess compatibility;
- grant install authority by creating a proposal;
- grant launch authority after installation;
- grant update authority;
- switch the active desktop version;
- grant rollback authority.

The existing package-plan approval still authorizes the bounded artifact install action. The v0.50 proposal is an additional release-lineage prerequisite, not a replacement authority token.

See [docs/PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md](docs/PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md).
