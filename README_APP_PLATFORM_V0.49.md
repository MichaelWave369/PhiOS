# PhiOS App Platform v0.49

**A successful release build must keep the exact human-review lineage that allowed it to execute.**

v0.49 carries the exact v0.48 release-build review digest into the canonical build execution receipt and preserves that lineage through offline npm execution and package planning.

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
    offline build receipt
        ↓
    lineage-bound package plan / review

The central boundary remains:

    successful release build
    ≠ install authority
    ≠ update authority

## Execution receipts

Current build execution receipts use:

    phios.build_execution_receipt.v0.2

They carry:

    release_build_review_sha256 = <exact v0.48 digest or null>

That field participates in the canonical execution receipt SHA-256.

Changing or removing the release-review lineage therefore changes the execution receipt digest and invalidates downstream receipts that bind it.

Ordinary builds emit an explicit null lineage value.

## Offline npm builds

A derived offline npm BuildPlan preserves release advancement lineage from its parent plan.

If that derived plan contains release lineage, offline execution requires the exact v0.48 review for the derived plan plus the exact approved review digest.

The resulting build execution receipt carries that digest, and the existing v0.32 offline receipt already binds the exact build execution receipt SHA-256.

## Package planning

Current package plans use:

    phios.build_package_plan.v0.2
    phios.build_package_plan_review.v0.2

The exact release-build review digest is carried into both the package plan and its review surface.

The package-plan SHA therefore binds the release lineage before installation review.

Legacy ordinary v0.1 build execution receipts and v0.1 package plans remain readable without inventing release lineage.

## Non-authority

v0.49 records provenance. It does not create authority.

A successful build, offline build, package plan, or package review still does not grant:

- compatibility authority;
- permission-grant authority;
- install authority;
- update authority;
- launch authority.

See [docs/PHIOS_APP_PLATFORM_V0.49_RELEASE_EXECUTION_LINEAGE.md](docs/PHIOS_APP_PLATFORM_V0.49_RELEASE_EXECUTION_LINEAGE.md).
