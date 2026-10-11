# PhiOS v0.65: frontend dependency graph freeze

**Status: capture candidate. Do not merge before reviewed lockfiles are committed,
the CI job uses only them, and exact-source npm CI builds pass.**

Vessie web source: `69a558ea2d1e8b361e05ded9bed4fc27b32e30cd`.
ThinkTank source: `1e8084a684ccf400c37d05d8bfe992680a72e887`.
Both upstream checkouts currently have `package.json` but **no**
`package-lock.json`.

## Two-stage, reviewed change

1. Obtain npm v3 lockfile candidates via the official Node/npm resolver against
   the **exact pinned source checkouts**. Run `npm install --package-lock-only
   --ignore-scripts` so dependency scripts do not execute.
2. Commit the reviewed generated lockfiles **only inside PhiOS**, with separate
   immutable SHA-256 provenance for each source package manifest.
3. In the real Trellis staging CI, verify the checkout revision and manifest
   digest, refuse unexpected upstream locks, verify the known lockfile hash,
   and copy the PhiOS-owned snapshot into each ephemeral source checkout.
   Install **only via `npm ci --ignore-scripts`**, never via dynamic
   `npm install`, before building and staging the two React frontends.
4. Independently run the same locked install and build in a second CI workflow,
   and require an exact installed graph replay before accepting it.

This freezes npm dependency **resolution and tarball-integrity metadata**
for a given source revision. It does not claim that public npm remains online,
that OS-dependent optional dependencies are identical across platforms, that
the final dist files are byte-for-byte reproducible, or that third-party
license, vulnerability and redistribution audits are complete.

Do not copy external application code, alter Vessie/ThinkTank upstream
sources, install anything into PhiOS, authorize model operations, ship an ISO,
or declare external DONE.

**Ledger Above Ego. DONE Means Verified.**
