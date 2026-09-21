# PhiOS App Platform v0.45

**Observed change is not a compatibility verdict.**

v0.45 adds a read-only structural comparison between the currently active governed app and one explicitly selected, exact-commit release candidate produced by v0.44.

The comparison is grounded in two independent provenance chains:

    active desktop bundle
        ↓
    verified install receipt
        ↓
    persisted build package plan
        ↓
    exact active repository + commit

and:

    selected GitHub release
        ↓
    exact tag → commit resolution
        ↓
    exact-commit v0.26 intake
        ↓
    digest-bound v0.44 candidate envelope

PhiOS then observes a closed set of root build markers at both exact commits and compares those object identities alongside the active and candidate manifests.

## What v0.45 reports

Manifest observations include:

- version changed
- name changed
- description changed
- runtime changed
- entrypoint target changed
- license expression changed
- redistribution declaration changed
- permissions added / removed

Build-marker observations include:

- marker added
- marker removed
- marker changed
- marker unchanged
- marker object type changed

The closed marker set includes package-manager metadata, lockfiles, Python/Rust/Go build files, static-web markers, and Vite/Netlify metadata already used elsewhere in the App Platform.

## What v0.45 does not report

v0.45 deliberately emits:

    compatibility_verdict = not_assessed
    build_authority = false
    install_authority = false
    update_authority = false

A changed package-lock.json is evidence of a changed package-lock.json. It is not automatically a security warning, compatibility failure, or update rejection.

Likewise, an added permission request is surfaced exactly as an added permission request. Human review remains responsible for deciding what it means.

## Operator flow

    phi-app compare-release-candidate \
      ACTIVE_BUNDLE_PATH \
      release-candidate-intake.json \
      --approve-release-candidate-intake-sha EXACT_SHA

The command independently revalidates the active app before making the comparison and refuses to compare a candidate from another app or repository.

## Exact-source comparison

v0.45 does not depend on whatever source tree happens to be on disk from an old build.

The active commit comes from the installed app's persisted build package plan, which is itself verified against the install receipt.

The candidate commit comes from the exact v0.44 candidate envelope.

For each commit, PhiOS asks GitHub only for the bounded root contents listing and extracts a closed marker set. It compares provider object IDs, object types, and byte counts without downloading changelog prose or arbitrary source files.

## Detailed contract

See [docs/PHIOS_APP_PLATFORM_V0.45_RELEASE_CHANGE_EVIDENCE.md](docs/PHIOS_APP_PLATFORM_V0.45_RELEASE_CHANGE_EVIDENCE.md).
