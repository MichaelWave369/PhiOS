# PhiOS App Platform v0.45 — Release Structural Change Evidence

## Status

Alpha contract.

Schema:

- phios.release_change_evidence.v0.1

Runtime surfaces:

- phios.apps.release_compatibility
- phi-app compare-release-candidate

## Purpose

v0.45 compares one currently active governed app with one explicitly approved v0.44 exact-commit release candidate and emits bounded structural change evidence.

The central rule is:

> A structural difference is evidence. It is not a compatibility verdict and it grants no mutation authority.

v0.45 does not rank candidates, assess overall safety, build source, install artifacts, or execute an update.

## Inputs

The comparison requires:

1. one active governed desktop bundle;
2. one phios.release_candidate_intake.v0.1 envelope;
3. the operator-approved exact candidate-envelope SHA-256;
4. configured installed-app, desktop-bundle, and desktop-entry roots.

An arbitrary repository URL is not accepted.

## Active provenance chain

Before observing source changes, PhiOS revalidates the active desktop bundle and installed ancestry using the existing desktop-update verification surface.

The active installed .phios/manifest.json is parsed as a v0.25 AppManifest and must still match the install receipt's manifest digest.

The persisted .phios/package-plan.json is parsed as a v0.33 BuildPackagePlan and must still match the install receipt's package-plan digest.

The package plan must bind the same manifest, app ID, app version, and repository as the active installation.

The exact active commit used for v0.45 source observation is the commit SHA from this verified package plan.

The install receipt is not widened to claim repository or commit facts it never contained.

## Candidate provenance chain

The supplied v0.44 candidate envelope is rejected unless:

- its canonical envelope digest is valid;
- the supplied operator approval equals that exact digest;
- its selected app ID matches the active app;
- its selected repository matches the active repository;
- its candidate manifest exists;
- the candidate manifest app ID and repository match the active app;
- intake evidence head SHA equals the selected candidate commit.

Tampering the nested intake while leaving the old digest causes rejection before any build-marker observation.

## Build-marker observation

The built-in GitHub provider reads one root contents listing at the exact active commit and one at the exact candidate commit.

The provider does not read arbitrary paths or download source-file contents.

Only this closed marker set is observed:

- package.json
- package-lock.json
- npm-shrinkwrap.json
- pnpm-lock.yaml
- yarn.lock
- bun.lock
- bun.lockb
- pyproject.toml
- Cargo.toml
- Cargo.lock
- go.mod
- go.sum
- index.html
- netlify.toml
- vite.config.js
- vite.config.ts

Each observed marker records:

- path;
- GitHub contents object type;
- byte count when supplied;
- provider object/blob identifier when supplied.

The provider response is bounded to 512 root entries.

## Marker comparison

For every path present in either exact commit, the evidence records one of:

- added
- removed
- changed
- unchanged
- type_changed

unchanged requires the same object type, provider object ID, and byte count.

v0.45 deliberately calls the GitHub object identifier provider_blob_id rather than SHA-256 because the Git contents API supplies Git object identity, not a PhiOS-computed SHA-256 of downloaded file bytes.

No release prose or changelog text participates in this comparison.

## Manifest comparison

The active and candidate manifests are compared descriptively.

The evidence may record:

- version_changed
- name_changed
- description_changed
- runtime_changed
- entrypoint_target_changed
- license_expression_changed
- redistribution_changed
- permissions_changed

Permission changes are additionally represented as exact sorted sets:

- permissions_added
- permissions_removed

No semantic version ordering is inferred.

A version change means only that the bounded manifest strings differ.

## Evidence identity

The canonical release-change evidence binds:

- app ID;
- repository URL;
- active/candidate version strings;
- exact active/candidate commit SHAs;
- active/candidate manifest SHA-256 values;
- exact approved candidate-intake SHA-256;
- active bundle path;
- active grant SHA-256;
- manifest change labels;
- permission additions/removals;
- exact marker change records;
- provider request count;
- fixed no-verdict/no-authority fields.

The artifact SHA-256 is computed from canonical JSON.

## No verdict

Every v0.45 artifact fixes:

    compatibility_verdict = not_assessed
    build_authority = false
    install_authority = false
    update_authority = false

There is no pass/fail, safe/unsafe, recommended/not-recommended, or compatibility score in v0.45.

Examples:

    package-lock.json changed
    ≠ dependency update is safe

    runtime changed
    ≠ candidate is incompatible

    permission added
    ≠ permission should be granted

Those are later human or separately governed decisions.

## CLI

Example:

    phi-app compare-release-candidate \
      ~/.local/share/phios/desktop-apps/APP_ID/BUNDLE \
      release-candidate-intake.json \
      --approve-release-candidate-intake-sha EXACT_SHA

The command prints the canonical structural evidence object.

It performs no filesystem mutation beyond ordinary process/library behavior and does not write an approval or update receipt.

## Relationship to v0.43 and v0.44

v0.44 determines which exact candidate is being discussed.

v0.45 describes structural differences between that candidate and the current active app.

v0.43 remains the destructive lifecycle gate. Even a perfectly ordinary-looking v0.45 diff cannot bypass unresolved lifecycle reconciliation.

## CI verification model

v0.45 tests cover:

- exact-commit GitHub root listing use;
- closed marker allowlist;
- manifest runtime/entrypoint/license/redistribution change reporting;
- permission additions;
- permission removals;
- added/removed/changed/unchanged marker classification;
- marker object-type change classification;
- exact candidate-envelope approval;
- candidate-envelope tamper rejection before provider calls;
- repository continuity;
- fixed not_assessed compatibility verdict;
- zero build/install/update authority.

## Explicit non-capabilities

v0.45 does not:

- select a release;
- rank a release;
- parse changelog prose;
- classify security risk;
- infer package vulnerability;
- claim API compatibility;
- claim ABI compatibility;
- execute dependency resolution;
- download arbitrary source files;
- build;
- install;
- update;
- grant permissions;
- issue a compatibility verdict.

## Planned next rung

A future v0.46 may add a bounded **Human Compatibility Review / Acceptance Record** that lets an operator acknowledge specific observed changes and bind that acknowledgement to the exact v0.45 evidence digest.

Such a record should still remain separate from build, install, and update execution authority.
