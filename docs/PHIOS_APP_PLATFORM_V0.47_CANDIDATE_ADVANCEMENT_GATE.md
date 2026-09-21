# PhiOS App Platform v0.47 — Candidate Advancement Gate

## Status

Alpha contract.

Schema:

- phios.release_candidate_advancement.v0.1

Runtime surfaces:

- phios.apps.release_advancement
- phi-app advance-release-candidate
- phi-app plan-build release-candidate gate

## Purpose

v0.47 makes the v0.46 human review record an enforced prerequisite before an explicitly selected release candidate may enter build planning.

The central rule is:

> Human review may satisfy a planning prerequisite. It does not grant build execution, install, or update authority.

v0.47 adds no source download, build execution, installation, permission grant, or update side effect.

## Reviewed chain

Candidate advancement requires three exact artifacts:

1. phios.release_candidate_intake.v0.1 from v0.44;
2. phios.release_change_evidence.v0.1 from v0.45;
3. phios.release_change_acceptance.v0.1 from v0.46.

The operator must also approve the exact v0.46 acceptance SHA-256.

All three artifacts are strictly reconstructed and their canonical digests are verified.

## Chain validation

v0.47 rejects the chain unless:

- v0.45 release_candidate_intake_sha256 equals the supplied v0.44 candidate intake;
- v0.46 release_change_evidence_sha256 equals the supplied v0.45 evidence;
- app IDs match across v0.44, v0.45, and v0.46;
- repositories match canonically across the chain;
- v0.45 active version equals the installed version recorded by v0.44 selection;
- v0.46 active version equals v0.45 active version;
- v0.45 candidate version equals the exact candidate manifest version from v0.44;
- v0.46 candidate version equals v0.45 candidate version;
- v0.45 candidate commit equals the exact selected v0.44 commit;
- v0.46 candidate commit equals v0.45 candidate commit;
- v0.46 active commit equals v0.45 active commit;
- v0.45 candidate manifest SHA-256 equals the exact v0.44 candidate manifest digest;
- operator-approved acceptance SHA-256 equals the exact v0.46 record.

No field is filled from guesswork.

## Advancement record

A successful advancement fixes:

    advancement_state = human_review_prerequisite_satisfied
    advancement_scope = build_planning_only
    compatibility_verdict = not_assessed
    acquisition_authority = false
    build_execution_authority = false
    install_authority = false
    update_authority = false

The record binds:

- v0.44 candidate-intake SHA-256;
- v0.45 change-evidence SHA-256;
- v0.46 acceptance SHA-256;
- app ID;
- repository;
- active version;
- candidate version;
- active exact commit;
- candidate exact commit;
- candidate manifest SHA-256.

The record has its own canonical SHA-256 and strict reconstruction.

## Build-planning enforcement

The ordinary v0.28 plan_build_from_payloads surface now distinguishes two cases.

### Ordinary app intake

Non-release intake behaves exactly as before.

Supplying release-advancement arguments to ordinary intake is rejected.

### Release-candidate intake

When the intake schema is phios.release_candidate_intake.v0.1, build planning fails unless all four gate inputs are supplied:

- v0.45 evidence;
- v0.46 acceptance;
- v0.47 advancement record;
- exact operator-approved v0.47 advancement SHA-256.

The gate is revalidated during build planning.

Therefore creating an advancement JSON once and later mixing it with a different candidate, evidence object, or acceptance record does not pass.

## BuildPlan provenance

After the gate passes, the existing v0.28 planner performs its normal acquisition-receipt and workspace validation.

The resulting canonical BuildPlan includes a note containing:

    release_candidate_advancement_sha256=<exact advancement digest>

This note participates in the BuildPlan digest.

The plan remains a non-executing declarative artifact.

## CLI

Create advancement:

    phi-app advance-release-candidate \
      release-candidate-intake.json \
      release-change-evidence.json \
      release-change-acceptance.json \
      --approve-release-change-acceptance-sha EXACT_ACCEPTANCE_SHA

Then plan the acquired candidate:

    phi-app plan-build \
      release-candidate-intake.json \
      source-acquisition-receipt.json \
      --release-change-evidence-json release-change-evidence.json \
      --release-change-acceptance-json release-change-acceptance.json \
      --release-candidate-advancement-json release-candidate-advancement.json \
      --approve-release-candidate-advancement-sha EXACT_ADVANCEMENT_SHA

No release-specific flag changes the ordinary source acquisition rules.

## Source acquisition ordering

v0.47 deliberately gates build planning, not source acquisition.

v0.27 source acquisition is already an exact-commit, exact-manifest, non-executing operation with separate explicit approvals.

This permits PhiOS to acquire bytes needed for investigation while still preventing the reviewed release candidate from entering a build plan before human change review is satisfied.

## Fail-closed behavior

v0.47 rejects:

- stale acceptance approval;
- stale advancement approval;
- cross-candidate v0.45 evidence;
- v0.46 acceptance bound to different evidence;
- app/repository/version/commit mismatch;
- candidate-manifest digest mismatch;
- malformed/tampered advancement records;
- release-candidate build planning without all gate artifacts;
- release gate arguments supplied to ordinary intake.

## CI verification model

v0.47 tests cover:

- exact reviewed-chain advancement success;
- zero acquisition/build-execution/install/update authority;
- stale v0.46 approval rejection;
- cross-candidate commit mismatch rejection;
- strict advancement-record round trip;
- advancement tamper rejection;
- full-chain revalidation;
- stale advancement approval rejection;
- release-candidate plan-build blocked without v0.47 gate;
- exact gated release-candidate build planning success;
- advancement digest bound into canonical BuildPlan notes;
- wrong advancement approval rejection;
- ordinary app builds rejecting irrelevant release-gate inputs;
- all existing ordinary v0.28 build-plan tests unchanged.

## Explicit non-capabilities

v0.47 does not:

- issue a compatibility verdict;
- grant a permission;
- grant build execution authority;
- grant install authority;
- grant update authority;
- execute a build;
- stage dependencies;
- install artifacts;
- switch the active desktop app;
- bypass v0.43 lifecycle gating.

## Planned next rung

v0.48 should add a **Release Build Review Binding**.

That rung can require the exact v0.47 advancement digest to remain bound through build-plan review and later release-build authorization, so a release candidate cannot shed its human-review lineage after planning.

The v0.48 review should still remain separate from build execution authority.
