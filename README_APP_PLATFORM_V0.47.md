# PhiOS App Platform v0.47

**Human review is now an enforced prerequisite for release-candidate build planning.**

v0.47 closes the gap between the v0.46 acceptance record and the ordinary v0.28 build planner.

A selected release candidate can no longer enter the generic build-planning path merely because its source was acquired. PhiOS now requires the exact reviewed chain:

    v0.44 release candidate intake
        ↓
    v0.45 structural change evidence
        ↓
    v0.46 human acceptance
        ↓
    v0.47 candidate advancement
        ↓
    v0.28 build planning

The advancement gate revalidates every link before allowing the build plan to be created.

## Candidate advancement

The operator creates the advancement record with:

    phi-app advance-release-candidate \
      release-candidate-intake.json \
      release-change-evidence.json \
      release-change-acceptance.json \
      --approve-release-change-acceptance-sha EXACT_SHA

The record binds:

- exact v0.44 candidate-intake digest;
- exact v0.45 evidence digest;
- exact v0.46 acceptance digest;
- app identity;
- repository;
- active/candidate versions;
- active/candidate exact commits;
- candidate manifest digest.

It fixes:

    advancement_state = human_review_prerequisite_satisfied
    advancement_scope = build_planning_only
    compatibility_verdict = not_assessed
    acquisition_authority = false
    build_execution_authority = false
    install_authority = false
    update_authority = false

## Enforced build-planning gate

For ordinary first-time app intake, plan-build behaves exactly as before.

For phios.release_candidate_intake.v0.1, plan-build now requires:

    --release-change-evidence-json
    --release-change-acceptance-json
    --release-candidate-advancement-json
    --approve-release-candidate-advancement-sha

The complete chain is revalidated during planning.

The resulting BuildPlan records the exact advancement SHA-256 in its canonical notes, so the plan digest itself changes if the advancement provenance changes.

## Meaning

    candidate reviewed
    ≠ candidate advanced

    candidate advanced
    ≠ build execution authorized

    build plan created
    ≠ build plan approved

    build plan approved
    ≠ install/update authorized

v0.47 advances eligibility only into deterministic non-executing build planning.

## Detailed contract

See [docs/PHIOS_APP_PLATFORM_V0.47_CANDIDATE_ADVANCEMENT_GATE.md](docs/PHIOS_APP_PLATFORM_V0.47_CANDIDATE_ADVANCEMENT_GATE.md).
