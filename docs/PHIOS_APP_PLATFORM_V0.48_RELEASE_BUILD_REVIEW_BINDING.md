# PhiOS App Platform v0.48 — Release Build Review Binding

## Status

Alpha contract.

Schema:

- phios.release_build_review.v0.1

Runtime surfaces:

- phios.apps.release_build_review
- phi-app review-release-build-plan
- release-aware BuildExecutionRequest validation
- phi-app execute-build release review gate
- phi-app execute-sandboxed-build release review gate

## Purpose

v0.48 preserves release-review lineage after v0.47 build planning and requires an exact release-specific review before a release-lineage BuildPlan may enter build execution.

The central rule is:

> Review lineage must survive planning. A release build review still grants no build execution, permission, install, or update authority.

## BuildPlan lineage detection

v0.47 writes the exact candidate advancement digest into the canonical BuildPlan notes:

    release_candidate_advancement_sha256=<exact digest>

v0.48 reads that binding deterministically.

Current v0.47 plans use one dedicated note.

For compatibility with the initial v0.47 emitted form, v0.48 also recognizes the earlier semicolon-suffixed note form.

A plan with multiple advancement bindings fails closed.

A malformed advancement digest fails closed.

No advancement binding means the plan is treated as an ordinary non-release BuildPlan.

## Release build review creation

The operator supplies:

1. one exact canonical BuildPlan;
2. one exact v0.47 ReleaseCandidateAdvancementRecord;
3. the operator-approved exact advancement SHA-256.

v0.48 rejects review creation unless:

- operator approval equals the exact advancement digest;
- the BuildPlan contains exactly one release advancement binding;
- that binding equals the supplied advancement digest;
- app ID matches;
- repository matches canonically;
- BuildPlan commit equals advancement candidate commit;
- BuildPlan manifest SHA-256 equals advancement candidate manifest SHA-256.

## Review record

A successful phios.release_build_review.v0.1 record binds:

- release_candidate_advancement_sha256;
- build_plan_sha256;
- app_id;
- repository_url;
- commit_sha;
- manifest_sha256;
- source_snapshot_sha256;
- plan_status;
- strategy;
- requested_build_permissions.

Requested permissions are canonically sorted and duplicate-free.

Every review fixes:

    review_state = reviewed_for_build_execution_consideration
    review_scope = exact_release_build_plan
    compatibility_verdict = not_assessed
    permission_grant_authority = false
    build_execution_authority = false
    install_authority = false
    update_authority = false

The review has its own canonical SHA-256 and strict reconstruction.

## Meaning of review

reviewed_for_build_execution_consideration means:

    A human-facing review artifact has been bound to this exact release BuildPlan.

It does not mean:

    the build is safe
    the build is compatible
    build permissions are granted
    build execution is authorized
    install is authorized
    update is authorized

Those remain separate decisions.

## Execution gate

BuildExecutionRequest is now release-aware.

If the BuildPlan contains release advancement lineage, request creation requires:

- one exact v0.48 review object;
- one exact operator-approved review SHA-256.

The review is reconstructed and revalidated against the current BuildPlan.

The execution request is rejected unless the review still matches:

- advancement digest;
- canonical plan SHA-256;
- app ID;
- repository;
- commit;
- manifest digest;
- source snapshot digest;
- plan status;
- strategy;
- requested build permissions.

A review bound to another BuildPlan therefore cannot authorize request creation even if the two plans look similar.

## Ordinary builds

Ordinary BuildPlans without release lineage retain the existing v0.29 execution-request behavior.

Supplying release-review inputs to an ordinary BuildPlan is rejected.

This prevents release-review artifacts from becoming generic authority tokens.

## CLI

Review one release BuildPlan:

    phi-app review-release-build-plan \
      build-plan.json \
      release-candidate-advancement.json \
      --approve-release-candidate-advancement-sha EXACT_ADVANCEMENT_SHA

Then create/execute a normal build request:

    phi-app execute-build \
      build-plan.json \
      source-acquisition-receipt.json \
      --approve-plan-sha EXACT_PLAN_SHA \
      --approve-source-sha EXACT_SOURCE_SHA \
      --release-build-review-json release-build-review.json \
      --approve-release-build-review-sha EXACT_REVIEW_SHA \
      [--allow-build-permission ...]

The sandboxed command accepts the same release-review pair.

## Existing execution approvals remain required

v0.48 does not replace v0.29 approvals.

Release execution still requires:

- exact approved BuildPlan SHA-256;
- exact approved source snapshot SHA-256;
- exact requested build-permission set;
- all existing tool/network/workspace checks.

v0.48 adds the release-lineage review prerequisite on top of those existing controls.

## Fail-closed behavior

v0.48 rejects:

- stale advancement approval during review creation;
- BuildPlan bound to another advancement;
- multiple advancement bindings;
- malformed advancement binding;
- tampered review record;
- stale review approval;
- review bound to another BuildPlan;
- app/repository/commit/manifest mismatch;
- source snapshot mismatch;
- plan-status mismatch;
- strategy mismatch;
- requested-permission mismatch;
- release execution without v0.48 review;
- release review supplied to ordinary execution.

## CI verification model

v0.48 tests cover:

- exact advancement-to-plan review binding;
- initial v0.47 embedded-note compatibility;
- duplicate advancement binding rejection;
- exact advancement approval requirement;
- cross-plan advancement rejection;
- strict review round trip;
- review tamper rejection;
- release execution blocked without v0.48 review;
- exact v0.48 review allowing BuildExecutionRequest creation;
- stale review approval rejection;
- review bound to another plan rejection;
- ordinary build execution unchanged;
- ordinary build rejection of irrelevant release-review inputs.

Because normal and sandboxed CLI execution both construct BuildExecutionRequest through the same from_payloads surface, the release-review gate applies to both.

## Explicit non-capabilities

v0.48 does not:

- execute source during review;
- issue a compatibility verdict;
- grant build permissions;
- grant build execution authority;
- grant install authority;
- grant update authority;
- bypass sandbox policy;
- bypass exact BuildPlan approval;
- bypass source-snapshot approval;
- bypass v0.43 lifecycle gating.

## Planned next rung

v0.49 should carry the exact v0.48 release build review lineage into the build execution receipt and later package/install planning.

That will let PhiOS prove that a produced release artifact came from the exact reviewed release candidate without treating successful execution as install or update authority.
