# PhiOS App Platform v0.48

**A reviewed release candidate cannot shed its human-review lineage before build execution.**

v0.48 binds one exact v0.47 candidate advancement record to one exact gated BuildPlan and requires that binding again when a release-lineage build enters the execution-request surface.

The lineage is now:

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
    execution request

Ordinary first-time app builds continue to use the existing review/execution path unchanged.

## Release build review

The operator creates the review record with:

    phi-app review-release-build-plan \
      build-plan.json \
      release-candidate-advancement.json \
      --approve-release-candidate-advancement-sha EXACT_SHA

The review binds:

- exact v0.47 advancement SHA-256;
- exact canonical BuildPlan SHA-256;
- app ID;
- repository;
- exact candidate commit;
- manifest SHA-256;
- source snapshot SHA-256;
- build-plan status;
- build strategy;
- exact requested build permissions.

It fixes:

    review_state = reviewed_for_build_execution_consideration
    review_scope = exact_release_build_plan
    compatibility_verdict = not_assessed
    permission_grant_authority = false
    build_execution_authority = false
    install_authority = false
    update_authority = false

## Execution enforcement

A BuildPlan with release advancement lineage cannot create a BuildExecutionRequest unless the exact v0.48 review record and exact review approval are supplied.

Both normal and sandboxed build commands use the same BuildExecutionRequest surface, so the gate applies to both.

Ordinary non-release BuildPlans reject irrelevant release-review inputs.

## Detailed contract

See [docs/PHIOS_APP_PLATFORM_V0.48_RELEASE_BUILD_REVIEW_BINDING.md](docs/PHIOS_APP_PLATFORM_V0.48_RELEASE_BUILD_REVIEW_BINDING.md).
