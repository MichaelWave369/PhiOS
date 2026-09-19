# PhiOS App Platform v0.28 — Build Plan Contract

## Status

Alpha contract.

Schemas:

- `phios.build_plan.v0.1`
- `phios.build_plan_review.v0.1`

## Purpose

v0.28 turns an acquired source workspace into a deterministic, reviewable **proposal** for future
build execution.

It does not execute the proposal.

## Inputs and binding

Planning requires:

1. the v0.26 intake result containing the v0.25 manifest candidate;
2. a successful v0.27 acquisition receipt.

The planner rejects mismatches in:

- app ID;
- repository URL;
- exact commit SHA;
- canonical manifest SHA-256.

The acquisition workspace must exist as a local directory.

## Current-source snapshot

Before reading build metadata, v0.28 recursively inspects the current local source workspace with
bounded file, directory, and byte limits.

It rejects:

- symlinks;
- special files;
- unsafe relative paths;
- files larger than the acquisition-era per-file bound;
- excessive file/directory/byte counts.

The planner compares current file count and total bytes to the acquisition receipt.

It then computes a separate `source_snapshot_sha256` from sorted canonical records containing:

```text
relative POSIX path
byte count
SHA-256(file bytes)
```

This digest deliberately excludes filesystem executable-mode metadata. The v0.27 acquisition tree
digest already preserves the archive-normalized mode-bearing identity, while that mode information
is not consistently representable on every supported host filesystem.

The two digests therefore make different claims and are not silently treated as interchangeable.

A later executor should recompute `source_snapshot_sha256` immediately before build execution.

## Bounded build metadata

Only known root metadata files are interpreted, including:

- `package.json`;
- package-manager lockfiles;
- `pyproject.toml`;
- `Cargo.toml` / `Cargo.lock`;
- `go.mod` / `go.sum`;
- `index.html`;
- selected Vite/Netlify markers.

Each interpreted metadata file is capped at 256 KiB.

The plan persists hashes and byte counts of observed metadata files, not their raw contents.

## Node planning

Node package-manager selection considers:

- npm lockfiles;
- `pnpm-lock.yaml`;
- `yarn.lock`;
- Bun lockfiles;
- the bounded `packageManager` declaration in `package.json`.

Conflicting package-manager evidence yields `review_required`.

Locked dependency commands are preferred when evidence supports them.

Examples:

```text
npm ci
pnpm install --frozen-lockfile
yarn install --immutable
bun install --frozen-lockfile
```

If a `build` script exists, the plan proposes only the package-manager invocation:

```text
PACKAGE_MANAGER run build
```

The repository's script body is not copied into a shell command by PhiOS.

Known output conventions are narrowly recognized for Vite, Next.js, and react-scripts. Unknown
output topology yields `review_required`.

## Python planning

A root `pyproject.toml` can produce a proposed PEP 517 wheel step:

```text
python -m build --wheel --outdir .phios-build/out .
```

The plan records that isolated build dependencies may require network access.

## Cargo planning

A Cargo plan proposes a release build.

When `Cargo.lock` is present:

```text
cargo build --release --locked
```

Without a lockfile the plan remains `review_required`.

## Go planning

A Go module can produce:

```text
go build ./...
```

v0.28 does not infer final Go binary topology, so Go plans remain `review_required`.

## Static web planning

A static web app with no package build metadata requires no build execution.

Its entrypoint is recorded as the expected source artifact.

## Plan identity

Canonical JSON for the plan body is SHA-256 hashed.

The emitted `plan_sha256` is not itself included in the hashed body.

Changing any bound input, source snapshot, strategy, command argv, permission request, expected
output, or note changes the plan digest.

## Build permissions

A plan may request:

- `build.network.dependencies`;
- `build.process.execute`;
- `build.workspace.write`.

These identifiers are declarative requests.

v0.28 does not grant authority and does not check whether a future grant should be issued.

## Explicit non-capabilities

v0.28 does not:

- execute subprocesses;
- invoke a shell;
- run package managers;
- download dependencies;
- invoke compilers;
- write build outputs;
- register an app;
- launch an app;
- grant build/runtime permissions;
- promote trust.

## Planned next rung

v0.29 will add a **Build Execution Contract**.

That rung should require explicit approval of:

- exact `plan_sha256`;
- exact `source_snapshot_sha256`;
- requested build permissions.

Immediately before execution, it should recompute the source snapshot and fail closed if the bytes
changed after review.

Execution receipts should bind tool versions, step outcomes, output hashes, and the approved plan.
