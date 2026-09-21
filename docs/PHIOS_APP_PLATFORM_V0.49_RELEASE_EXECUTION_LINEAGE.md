# PhiOS App Platform v0.49 — Release Execution Lineage

## Status

Alpha contract.

Current schemas:

- phios.build_execution_receipt.v0.2
- phios.build_package_plan.v0.2
- phios.build_package_plan_review.v0.2

Compatibility readers retained:

- phios.build_execution_receipt.v0.1 at the package-binding boundary
- phios.build_package_plan.v0.1

## Purpose

v0.48 proved that one exact reviewed release BuildPlan was allowed to enter build execution request creation.

v0.49 proves that the resulting execution evidence cannot silently shed that review lineage before package planning.

The central rule is:

> Build success is evidence about execution. It is not install or update authority.

## Canonical execution lineage

BuildExecutionRequest already carries the exact validated v0.48 release-build review SHA-256 for release-lineage plans.

v0.49 writes that digest into every current BuildExecutionReceipt:

    release_build_review_sha256=<exact v0.48 digest>

For ordinary builds:

    release_build_review_sha256=null

The field is part of the canonical execution-receipt body. It therefore participates in:

    receipt_sha256 = SHA256(canonical execution receipt)

Changing the lineage changes the receipt digest.

Malformed non-null lineage digests fail closed.

## Offline npm lineage

v0.32 derives a new offline BuildPlan from a reviewed npm BuildPlan.

That derived plan retains the original notes, including the v0.47 release-candidate advancement binding.

Because the derived plan is a distinct canonical BuildPlan, a release offline build must be reviewed against that exact derived plan.

For a release-lineage offline plan, NpmOfflineBuildRequest now requires:

- the exact v0.48 release-build review object;
- the exact approved v0.48 review SHA-256.

The review is revalidated against the derived BuildPlan before execution.

The exact validated review digest is copied into the underlying BuildExecutionRequest and therefore into the v0.2 BuildExecutionReceipt.

The existing v0.32 NpmOfflineBuildReceipt already binds:

    build_execution_receipt_sha256

So the offline receipt transitively binds the release review without gaining any new authority.

## Package lineage

SuccessfulBuildBinding accepts:

- legacy ordinary phios.build_execution_receipt.v0.1;
- current phios.build_execution_receipt.v0.2.

For v0.2, it validates and exposes release_build_review_sha256.

BuildPackagePlan v0.2 carries that exact value.

BuildPackageReview v0.2 exposes it for human inspection.

The package-plan SHA-256 therefore covers:

- app and version;
- manifest and registry snapshot;
- repository and commit;
- build-plan digest;
- execution-receipt digest;
- offline-build receipt digest;
- artifact-set digest and exact artifacts;
- install-relative path;
- exact release-build review digest or null;
- launch_authority=false.

## Legacy compatibility

Legacy v0.1 execution receipts contain no release_build_review_sha256 field.

They may still be consumed by package planning as ordinary non-release evidence if their exact canonical digest and all existing v0.33 constraints validate.

Legacy v0.1 package plans remain strictly reconstructible with their historical field set and digest. They cannot carry v0.49 release lineage.

No legacy artifact is silently upgraded into release provenance.

## Authority boundaries

v0.49 does not grant:

    compatibility authority
    permission authority
    build execution authority beyond the already-approved request
    install authority
    update authority
    launch authority

The relevant implications are intentionally one-way:

    valid v0.48 review
        + approved execution request
        + successful execution
        → lineage-bound execution evidence

    lineage-bound execution evidence
        + valid offline receipt
        → lineage-bound successful-build evidence

    lineage-bound successful-build evidence
        → package planning may describe exact artifacts

But:

    successful build
    ≠ safe to install

    package plan
    ≠ install approval

    release lineage
    ≠ update authority

## Fail-closed behavior

v0.49 rejects:

- malformed release-build review digest in a v0.2 execution receipt;
- release offline execution without an exact v0.48 review;
- stale or mismatched v0.48 review approval during offline execution;
- release review inputs supplied to an ordinary offline plan;
- unsupported execution-receipt schemas at package binding;
- unknown fields in legacy or current execution receipts;
- tampered execution-receipt digests;
- tampered offline-build receipt digests;
- artifact-set drift;
- unsupported package-plan schemas;
- release lineage inserted into a legacy v0.1 package plan.

## Tests

The v0.49 tests cover:

- exact review digest changes the canonical execution receipt SHA;
- ordinary receipts carry explicit null lineage;
- package plan and review preserve exact release lineage;
- malformed lineage digest rejection;
- package-plan digest changes with lineage;
- legacy v0.1 execution receipt compatibility;
- legacy v0.1 package-plan round trip;
- derived offline release execution requires v0.48 review;
- derived offline execution preserves the exact review digest into the execution receipt;
- the v0.32 offline receipt continues binding that exact execution receipt.

## Next boundary

The next rung should govern the point where lineage-bound release artifacts are proposed for installation or update.

That future step must keep the same rule:

    evidence that an artifact came from the reviewed release chain
    ≠ authority to replace the active installed version
