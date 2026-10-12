# PhiOS App Platform v0.58 — Repository Profiler and Compatibility Classifier

## Status

Alpha contract.

New schemas:

- `phios.repo_profile.v0.1`
- `phios.repo_compatibility.v0.1`

## Purpose

The App Platform now has a governed toolchain/runtime spine through v0.57.

v0.58 pivots back to the operator-facing goal:

> Given a public GitHub repository, tell the operator what PhiOS can currently do with it and why.

The first user path is:

```text
GitHub URL
  -> bounded v0.26 intake
  -> v0.58 repository profile
  -> v0.58 compatibility assessment
  -> exact next gate or remediation
```

The central rule is:

> Compatibility is an advisory observation, not acquisition, build, install or launch authority.

## Inputs

v0.58 consumes the existing bounded v0.26 `AppIntakeResult`.

It does not clone the repository or recursively scan source code.

The profile records:

- public repository URL;
- owner/name;
- exact observed head SHA;
- archive/disabled state;
- intake status;
- declared/inferred/absent manifest source;
- app ID;
- runtime and target;
- manifest/proposal license expression;
- GitHub-reported SPDX identifier when available;
- normalized license state;
- deterministic build-family classification;
- bounded root markers;
- root `.gitmodules`, `.gitattributes`, and `.lfsconfig` marker presence.

## First compatibility policy

The first policy is deliberately tailored to the stated PhiOS acceptance corpus:

```text
license_policy = mit_only
```

Accepted automatic corpus evidence requires both the manifest/proposal and GitHub's
reported SPDX metadata to resolve to the MIT family:

- `MIT`
- `MIT-0`

A declared MIT manifest with no matching GitHub SPDX observation is held for review.
Conflicting license evidence is also held.

This is not a legal conclusion and `mit_reported` is deliberately not named
"legally verified." Other licenses are merely outside the first automatic acceptance
corpus and need explicit review.

## Build-family classification

v0.58 recognizes:

- `static_web`
- `node_npm`
- `node_pnpm`
- `node_yarn`
- `node_bun`
- `node_unlocked`
- `python_pep517`
- `rust_cargo`
- `go_module`
- `unknown`

The classifier uses only bounded intake evidence and root marker names.

It does not infer dependency safety from package-manager metadata.

## Compatibility statuses

v0.58 emits exactly one primary status:

```text
SUPPORTED_AFTER_OPERATOR_APPROVAL
REPOSITORY_DISABLED
ARCHIVED_REPOSITORY_REVIEW
NOT_AN_APPLICATION
MANIFEST_REVIEW_REQUIRED
LICENSE_REVIEW_REQUIRED
SUBMODULE_REQUIRED
LFS_REVIEW_REQUIRED
MISSING_TOOLCHAIN
LOCKFILE_REQUIRED
UNSUPPORTED_RUNTIME
```

### Supported after operator approval

This means only:

> No blocker visible to v0.58 was observed.

It does not mean the app is safe or runnable.

Later gates still apply:

- v0.27 exact source acquisition;
- build planning;
- toolchain/dependency checks;
- v0.57 selected-backend execution where applicable;
- artifact verification;
- install review;
- runtime/desktop launch review.

### Submodules

A root `.gitmodules` marker produces `SUBMODULE_REQUIRED`.

v0.27 acquires one exact GitHub commit ZIP and does not recursively acquire Git submodule
content.

v0.58 therefore refuses to pretend that the acquired tree would be complete.

### Git LFS review

A root `.gitattributes` or `.lfsconfig` marker produces
`LFS_REVIEW_REQUIRED`.

Presence of `.gitattributes` does not prove Git LFS is used. The status intentionally
means review is needed before claiming that ordinary archive bytes are complete source.

A later rung can inspect bounded attribute content and distinguish ordinary attributes
from actual LFS pointer use.

### Node package managers

The current capsule line supports Node/npm but not pnpm, Yarn or Bun.

Those managers therefore produce `MISSING_TOOLCHAIN`.

A Node project with no supported deterministic root lockfile produces
`LOCKFILE_REQUIRED`.

### Native runtimes

Rust/Cargo and Go build families are recognized, but the current installed-app runtime
does not launch native application artifacts.

They therefore produce `UNSUPPORTED_RUNTIME` rather than a false end-to-end support
claim.

### Python

An inferred `pyproject.toml` candidate does not identify the direct executable Python
entrypoint required by the current runtime adapter.

A Python repo reaches the supported class only when a valid declared
`phios-app.json` names an explicit `.py` target.

## Authority fields

Every profile fixes:

```text
profile_authority = false
acquisition_authority = false
build_authority = false
install_authority = false
launch_authority = false
```

Every compatibility assessment fixes:

```text
advisory_only = true
acquisition_authority = false
build_authority = false
install_authority = false
launch_authority = false
```

## Operator command

v0.58 adds:

```bash
phi-app profile-github https://github.com/OWNER/REPO
```

The command performs bounded public intake and prints the profile plus compatibility
assessment as JSON.

It does not automatically advance into acquisition.

## Exact source-size limitation

v0.58 intentionally does not guess whether a repository fits the v0.27 archive limits
from GitHub's approximate repository-size metadata.

The exact v0.27 acquisition boundary remains authoritative for:

- 16 MiB compressed archive;
- 4,096 regular files;
- 8 MiB per file;
- 128 MiB total uncompressed regular-file content.

A future profiler rung may add a bounded preflight size observation, but it must remain
distinct from exact acquisition evidence.

## Next boundary

v0.59 should add an operator-reviewed **Install from GitHub proposal** that binds:

- one exact v0.58 profile/assessment;
- one exact v0.26 intake result;
- the exact commit to be acquired;
- the proposed next governed stages.

The proposal should stop immediately on a v0.58 blocker and should never convert
`SUPPORTED_AFTER_OPERATOR_APPROVAL` into automatic acquisition authority.
