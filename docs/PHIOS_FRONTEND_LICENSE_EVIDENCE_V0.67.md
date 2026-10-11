# PhiOS v0.67: installed frontend dependency and license-evidence ledger

**Evidence collection and review queue only. Redistribution is NOT cleared.**

## Scope and source of truth

This extends v0.65's exact pinned npm graphs and v0.66's same-runner
two-clean-build comparison, for the same immutable Vessie/ThinkTank React
frontends. The separate lockfile CI job runs on an Ubuntu GitHub runner
with Node v24.21.0/npm v11.19.0 and the reviewed `npm ci --ignore-scripts`
install, **immediately before any Vite build can create temporary
cache files**. It inventories **the npm packages actually present under
`node_modules`**, rather than treating all optional, platform-specific
lockfile entries as installed.

For each app, `scripts/audit_frontend_license_evidence.py`:

1. Rechecks the exact upstream source SHA, source `package.json` SHA-256,
   and PhiOS-owned lockfile SHA-256 using the existing independent guard.
   It requires the installed checkout's lockfile to equal the reviewed bytes.
2. Walks the installed top-level and nested `node_modules` package
   directories (including scoped packages). It ignores npm's synthetic
   `.bin` launcher directory and checks npm's hidden package-lock file.
   It rejects linked package directories, unexpected hidden entries,
   untracked packages, missing **required** locked dependencies, and
   mismatches in installed package names/versions.
3. Records every installed npm component's lockfile path, name, version,
   corresponding registry integrity field, license declaration,
   development/optional flags and evidence from root-level LICENSE,
   LICENCE, COPYING, NOTICE, UNLICENSE and PATENTS files. The latter are
   stored as **filename, SHA-256 and byte length** only, not copied text.
4. Lists locked-but-absent optional platform packages separately. Any
   missing declared license, nonstandard legacy declaration, or package
   without root-level legal-file evidence enters an explicit human-review
   queue. An unrecognized or ambiguous license is never automatically
   treated as approved.
5. Writes a deterministic component manifest hash and a full, bounded
   JSON evidence report for each app as a GitHub Actions artifact.
   Unit tests include unknown licensing, extraneous/missing packages,
   tampered versions, linked license documents and symlinked packages.

## Evidence interpretation

A green workflow means the **installed dependency identities were matched
to the reviewed lock and the license/notice metadata ledger was created**.
This is useful preparation for a human license and distribution review.
It does **not** mean every license has been legally reviewed, permissions
confirmed, required notices assembled, or redistribution granted.

An installed dependency without a root LICENSE file can still have a valid
license in another location; the report records it as **needs review**, not
"illegal." Conversely, a declared MIT or Apache license does not by
itself establish that all attribution and packaging obligations have
been satisfied.

The npm census is on **one Linux CI platform**. Optional platform
dependencies absent here still need review before releases on Windows,
other architectures, or other Linux distributions. Static bundles may
also include third-party code or assets whose obligations require
separate review. No SBOM of the entire PhiOS operating system is claimed.

There is **no license clearance, vulnerability audit, production app
installation, desktop launch authority, provider/model execution,
distribution or external DONE** from this experiment. Upstream repositories,
the Trellis release artifact and PhiOS images are not modified.

**Ledger Above Ego. DONE Means Verified.**
