# PhiOS v0.60: Trellis staging bridge (first two React applications)

**Status: source-pinned artifact staging and verification only.**

This is the first functional link between the **v0.58 all-public-repo catalog**, the **v0.59 Vessie/ThinkTank application candidates**, and the separate first-party **Trellis 1.0.0-rc1** local-first Rust package manager.

It **does not install Vessie or ThinkTank into the real PhiOS system**. It does not grant an XDG desktop launcher, modify the system PhiOS app registry, run models, or bundle the Trellis executable on an ISO. The current v0.25–v0.57 PhiOS App Platform remains the sole source of installation and execution authority.

## Pinned sources

| Source | Reviewed fixed SHA | Purpose |
| --- | --- | --- |
| PhiOS v0.59 candidate set | loaded from current reviewed candidate JSON | application IDs, source repository, asset paths and denied authority |
| SuperPhiVessel | `69a558ea2d1e8b361e05ded9bed4fc27b32e30cd` | genuine React build, **`--base ./`** rather than its public Pages subpath |
| ThinkTank | `1e8084a684ccf400c37d05d8bfe992680a72e887` | genuine React build, **`--base ./`** rather than assuming root URLs |
| Trellis | `c4036f38e8b635709d069e505506191dfccf8c5c` | reviewed Trellis PR #12 source (CI-green, not yet merged); actual compiled CLI in ephemeral CI |

Trellis is a **separate repository licensed AGPL-3.0-only**. PhiOS v0.60 references its public, immutable commit for ephemeral CI testing, but does not copy its source into PhiOS, ship its binary in an ISO, or treat the declared MIT license of frontend projects as Trellis's license. Shipping a Trellis binary or modified Trellis source later requires deliberate AGPL compliance, notices and independent dependency/package review.

## Staging contract

`scripts/trellis_stage_bridge.py` has three commands:

- `plan APP`: checks the v0.59 candidate set with the **existing** `AppManifest.from_dict` validator; returns an inert JSON proposal. No external calls or writes.
- `stage APP --checkout FIXED_LOCAL_SOURCE --output NEW_TEMP_DIR`: checks the checkout's real Git HEAD against the exact reviewed SHA, inspects the already-built static frontend, refuses symlinks/hardlinks/special files, limits the payload to 2,048 files/64 MiB, and requires a React HTML entrypoint with relative JS and compiled CSS assets. Copies only actual compiled files into a **new** staging directory. Rehashes the staged payload against the source and writes a constrained `*.trellis.yaml` with `source.type:local_dir`, required SHA-256 checksum, no binaries, no dependencies, no postinstall command and a `phios-untrusted-staging-only` registry label. Staging has **zero** PhiOS installation authority. The output receipt includes each file's SHA-256 and a copy-integrity digest.
- `verify-staged --staging TEMP_DIR --trellis-home TEMP_HOME`: after an **independent** Trellis CLI `init`, `validate`, `install --from`, and `verify` in an operator-selected disposable home, cross-checks the staged files, exact installed contents, Trellis receipts and profile lock records. It **rehashes each installed byte**, a check Trellis v1.0-rc1's own `verify` (focused on lock/receipt/bin existence) does not currently perform for arbitrary static web files. Fails on tampering, mismatched files, unsupported permissions or fabricated receipts.

The bridge uses **the same directory checksum layout** as pinned Trellis: sorted relative filenames, NUL, file bytes, then `0xff` per file. The bridge's separate per-file digests detect individual file drift and a final checksum binds the whole static tree. Neither checksum is a digital signature, package signer attestation or assurance about what browser JavaScript does at runtime.

## CI runs actual code, not just a mock plan

`.github/workflows/trellis-stage-bridge.yml` checks out exact immutable sources, compiles a real Trellis executable using `cargo build --release --locked`, and runs `npm ci` / actual Vite builds for the two frontend projects using **`--base ./`**. It stages both frontends and executes **real Trellis** `validate`, `install --from`, `verify` against only two temporary, isolated `TRELLIS_HOME` directories. It runs the bridge's independent postinstall file verifier for both and deliberately tampers with an installed file to prove verification refuses drift.

Only generated staging and test artifacts are in GitHub's ephemeral runner temporary directory. Nothing is written to the installed PhiOS AppRegistry, approved desktop-catalog root, host package manager or release ISO. The workflow contains no API keys, no live model execution and no GitHub write permission. A green job proves reproducible **CI staging at exact pinned source revisions**. It does **not** prove browser behavior fully offline, native Linux desktop launch, model inference, verified dependency-license closure, production installer behavior or QEMU boot with the apps.

## Manual reproduction (in a disposable Linux workstation)

Start with local clones at exactly the pinned commits above, a manually built Trellis 1.0-rc1 CLI and a pre-allocated disposable directory. Build each project with its documented `npm ci` followed by `npm run build -- --base ./`. From PhiOS source root:

```bash
python scripts/trellis_stage_bridge.py plan vessie-web
python scripts/trellis_stage_bridge.py stage vessie-web \
  --checkout /tmp/source/SuperPhiVessel --output /tmp/phi-vessie-staging
TRELLIS=/tmp/source/Trellis/target/release/trellis
"$TRELLIS" --home /tmp/phi-trellis-home init
"$TRELLIS" --home /tmp/phi-trellis-home validate \
  /tmp/phi-vessie-staging/phios-vessie-web.trellis.yaml
"$TRELLIS" --home /tmp/phi-trellis-home install --from \
  /tmp/phi-vessie-staging/phios-vessie-web.trellis.yaml
"$TRELLIS" --home /tmp/phi-trellis-home verify
python scripts/trellis_stage_bridge.py verify-staged \
  --staging /tmp/phi-vessie-staging --trellis-home /tmp/phi-trellis-home
```

Use **a different Trellis home for ThinkTank**. Do not run this experiment as root; do not point Trellis at existing PhiOS installed-app directories. The `source_sha` proves only that the checked-out local git HEAD equals the reviewed candidate commit; the immutable GitHub Action fetch adds the observed source provenance for CI. Upstream repository/commit identity, dependency integrity, signed lockfiles and the supply chain beyond those bounds require separate review.

## What comes after

**v0.61:** curated, license-reviewed artifact acquisition and sandboxed build planning that delegates through the existing PhiOS App Platform, plus real Chromium smoke tests against both **Trellis-installed** static frontends in offline mode. Then, only with real operator approval and replayable receipts, promote verified bundles to the v0.38 desktop launcher and v0.39 catalog.

**Future ISO profile:** allow user-selected, independently approved offline `PhiOS Ecosystem Packs`; retain a lean core ISO. Qualify the exact selected package set in QEMU, including offline startup and recovery. Do not quietly bundle 132 repos, auto-install applications, or bypass PhiOS's one-use execution and display grants.

**Ledger Above Ego. DONE Means Verified.**
