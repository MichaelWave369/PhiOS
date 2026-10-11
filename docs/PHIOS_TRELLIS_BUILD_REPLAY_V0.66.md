# PhiOS v0.66: two clean frontend builds, exact output comparison

**Scope:** same-host byte-for-byte frontend bundle replay for two pinned,
PhiOS-staged React applications. This is a stricter gate than v0.65's
dependency graph freeze. It is not installation or redistribution clearance.

## Immutable inputs

Both replay builds use the exact pinned source Git commits and PhiOS-owned
reviewed npm lockfile snapshots already enforced in
[PhiOS v0.65](PHIOS_TRELLIS_DEPENDENCY_LOCKS_V0.65.md):

| Application | Pinned upstream revision | Frozen lockfile SHA-256 |
| --- | --- | --- |
| Vessie web | `69a558ea2d1e8b361e05ded9bed4fc27b32e30cd` | `4e0ac5153f3bc47cd78b4f5cfa42c2ede4dbfef8110a2d5deda49d5c81bd6c2a` |
| ThinkTank web | `1e8084a684ccf400c37d05d8bfe992680a72e887` | `251e461cdd11acf49f5c25eb58f0400a66daef1e6bb76486fc7a5f1fb22feffd` |

## Exact same-runner experiment

1. The original CI checkout for each app is validated against the immutable
   upstream commit and SHA-256 of its package manifest. The only additional
   file staged is its byte-verified reviewed lockfile.
2. Build **A** installs from a clean npm dependency tree with
   `npm ci --ignore-scripts --no-audit --no-fund` and runs the production
   `npm run build -- --base ./` command, using Node v24.21.0 and npm v11.19.0.
3. Replay **B** materializes a *separate* source directory from the same
   verified Git commit via `git archive` rather than copying build A's tree
   or using its node_modules. It checks package.json and copied lockfile
   SHA-256 before an independent `npm ci` and React build.
4. `scripts/verify_frontend_build_outputs.py` enumerates **all** regular
   files in each build's output folder (Vessie: `site/vessie`; ThinkTank:
   `dist`), rejects symlinks, hidden output files, incomplete output sets,
   and shared/nested source-output directories. It checks **exactly equal
   file sets and SHA-256 digests for every output file**.
5. It writes one JSON diagnostic receipt per app listing file hashes, a
   canonical manifest fingerprint, reviewed source and lock identities and
   explicit negative authority flags. Differences fail closed. Unit tests
   exercise a changed byte, added/removed assets, symlink, unreviewed app
   and shared-tree negative controls.

The experiment runs within the dedicated lockfile CI job and retains its
receipts. Other PhiOS workflows remain independent gates: the Trellis stage
still checks package bytes, Chromium mounts and navigation, disconnected
reloads, browser-process restart, and deliberate tamper rejection. Source
repositories and PhiOS installed images are untouched.

## Precise boundaries

A PASS proves **the two generated frontend file sets match byte for byte
across separate clean source trees on one GitHub runner** with one pinned
toolchain and dependency snapshot. It does *not* establish cross-runner or
cross-OS reproducibility, independently trusted tarball sources, full
cryptographic supply-chain provenance, the derived offline-profile build's
byte identity across runs, third-party license/redistribution clearance or
vulnerability absence.

This is not evidence that PhiOS has installed, launched or run models for
either app. No operator grant, production AppRegistry mutation, packaging
promotion, ISO release, or external DONE is authorized.

**Ledger Above Ego. DONE Means Verified.**
