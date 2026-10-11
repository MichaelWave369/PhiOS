# PhiOS v0.65: pinned npm dependency closure for two staged frontends

**Scope:** freeze dependency resolution for the exact reviewed versions of the
Vessie and ThinkTank React frontends. **Not** a license audit, complete
artifact-reproducibility attestation, or installation permission.

## Immutable sources, independently captured graph

| Source | Pinned git commit | Original package.json SHA-256 | PhiOS-owned package-lock SHA-256 |
| --- | --- | --- | --- |
| Vessie | `69a558ea2d1e8b361e05ded9bed4fc27b32e30cd` | `6bdbd921cea13474fc2b6fd5cbe02765345a48e345a9cc57913e9b0693e9664e` | `4e0ac5153f3bc47cd78b4f5cfa42c2ede4dbfef8110a2d5deda49d5c81bd6c2a` |
| ThinkTank | `1e8084a684ccf400c37d05d8bfe992680a72e887` | `2a593f3137545880115d0f2d112897038f52d0afeb01a144209947e59f49aaed` | `251e461cdd11acf49f5c25eb58f0400a66daef1e6bb76486fc7a5f1fb22feffd` |

The two standard npm v3 lockfiles were generated from these pinned upstream
checkouts, which had **no** existing package locks, using Node v24.21.0
and npm v11.19.0 with `npm install --package-lock-only --ignore-scripts`
on the CI runner. **No upstream repository files were committed or changed.**
PhiOS stores them under `dependency-locks/vessie-web/` and
`dependency-locks/thinktank-web/`.

Each snapshot pins resolved package versions and SHA-512 tarball integrity
metadata for the npm dependency graph. This does **not** incorporate third-party
source code directly into PhiOS. The application code remains at the exact
reviewed upstream commit, and third-party packages remain registry-resolved.

## CI enforcement

`scripts/verify_frontend_locks.py` verifies the source Git commit, exact
package.json SHA-256, original lockfile absence, exact PhiOS lockfile bytes
and SHA-256, root dependencies, `lockfileVersion=3`, approved npm registry
URLs, package paths, and package SHA-512 integrity. **Any mismatch fails**;
there is no dynamic registry resolution fallback.

The script copies only the approved lockfile into an **ephemeral GitHub CI
source checkout**. Both independent lock-validation CI and the full Trellis
packaging CI then run `npm ci --ignore-scripts --no-audit --no-fund`,
`npm ls --depth=0`, and the same React build commands. The Trellis workflow
still runs earlier app integrity gates, actual Chromium browser startup,
local interactions, disconnected reload, cold browser-process restart and
tamper-rejection controls.

## Explicit evidence limits

- The snapshot fixes npm dependency **resolution and integrity metadata**
  for these two **pinned revisions**, not every native platform or optional
  platform dependency installed by other operating systems.
- This is **not** byte-identical compiled output reproducibility across
  machines, registry mirror availability, or an independently verified
  Software Bill of Materials.
- This is **not** a transitive license/redistribution review or vulnerability
  clearance. It does not approve shipping the dependencies inside PhiOS.
- No installed PhiOS application, desktop launcher, local/cloud model usage,
  operator grant, or external DONE is authorized.

**Ledger Above Ego. DONE Means Verified.**
