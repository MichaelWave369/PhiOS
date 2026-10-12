# PhiOS v0.69: fail-closed application release evidence preflight

**This gate is not a release. The only acceptable positive result is
`HOLD_FOR_OPERATOR_REVIEW`.**

The reviewed Vessie and ThinkTank shells have accumulated CI evidence
through v0.60–v0.68: immutable upstream source and npm dependencies, Trellis
staging checks, disconnected browser start and restart, two clean compiled
frontend output trees with identical bytes on one GitHub runner, and a
Linux npm dependency/license-evidence ledger. None of this grants permission
to distribute these apps as PhiOS packages.

v0.69 adds an original evidence aggregation and **deny-by-default**
preflight to close the gap between *passing evidence* and *production
approval*. It runs entirely in GitHub's disposable CI directory. It never
contacts provider endpoints, installs an app in PhiOS, mutates release
manifests, changes upstream source, or packages native legal texts.

## What the gate actually consumes

The program `scripts/frontend_release_preflight.py` reads the **seven
fresh JSON receipts from the same frontend CI job**:

- v0.65 reviewed dependency lock and source verification for Vessie and
  ThinkTank, independently keyed to their pinned immutable upstream SHAs.
- v0.67 installed Linux `node_modules` component census and flagged legal
  evidence queue for each app. All package-list entries are hashed into
  a deterministic receipt manifest, and its exact four native-package
  human-review flags must remain present.
- v0.66 same-runner, separate-tree build replay receipts for each app,
  with file-path and SHA-256 manifest integrity checks.
- v0.68 immutable upstream source proofs (three actual MIT license files,
  one LZMA parent-package MIT declaration without a standalone license
  document), pinned to the four reviewed upstream source revisions and
  Git blob digests.

Every record must identify the correct reviewed app, source SHA and/or npm
lockfile hash, contain the expected schema/status, preserve *false*
install, model, external DONE and redistribution claims, and have a valid
canonical manifest digest. A missing, linked, mismatched or extra
unreviewed package or forged approval **fails the consistency gate**.

It writes `frontend-release-hold.json` with SHA-256 fingerprints of all
seven input reports, the two app identities, a seven-item release blocker
ledger, and **zero** authorization bits. This is a portable human-review
receipt, not a signed release artifact or a production registry entry.

## Why passing is still a HOLD

Seven open review obligations are frozen into this rung:

1. Standalone license documentation for the pinned native LZMA payload.
2. Reconciliation of Rollup's combined third-party license notices.
3. Source-to-published-binary provenance for each of the four native npm
   platform packages.
4. Transitive Rust licensing and other optional platform dependencies.
5. A reviewed distribution notice and attribution bundle.
6. Vulnerability assessment for the pinned dependency and distribution
   scope.
7. Separate founder/operator review and actual installation/distribution
   authorization.

Those are **unresolved**, not silently auto-cleared by present license
metadata. This release preflight does not implement an approval route.
Adding one later must be a separate, reviewed, human-authorized design
with narrowly scoped, independently verified evidence.

## CI negative-control behavior

The workflow runs the normal preflight and checks the result is HOLD. Then
it deliberately invokes the same code with
`--require-release-authority`. It **must exit nonzero**. The subsequent
test verifies a second generated packet still has every authority bit
false. If a future edit accidentally authorizes installation or
distribution, this negative control fails the CI workflow.

Unit tests exercise modified build digests, missing license review flags,
missing/symlinked receipts, unreviewed source revisions, forged grant fields,
and upstream source lock substitution. Previous frontend reproducibility,
license-source, offline Chromium and normal PhiOS qualification workflows
remain separate independent gates.

## Claims deliberately not made

This packet does not verify cross-platform binary reproducibility,
binary provenance from npm tarball to Git tag, license counsel approval,
complete SBOM, notarization, signed human release approval, OS image
installation, provider/model execution, complete security scanning or
external DONE.

**Ledger Above Ego. DONE Means Verified.**
