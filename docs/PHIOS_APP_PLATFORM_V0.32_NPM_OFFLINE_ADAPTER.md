# PhiOS App Platform v0.32 — npm Offline Dependency Adapter

## Status

Alpha contract.

Schemas:

- `phios.npm_cache_receipt.v0.1`
- `phios.npm_offline_build_plan.v0.1`
- `phios.npm_offline_build_plan_review.v0.1`
- `phios.npm_offline_build_receipt.v0.1`

## Purpose

v0.32 completes the first npm path from governed dependency acquisition to a network-denied build.

The central rule is:

> Network authority is removed only by creating and approving a new execution plan whose declared
> commands no longer require network access.

The original v0.28 build plan remains unchanged historical evidence.

## npm cache preparation

Input:

- one valid v0.31 dependency receipt;
- explicit approval of that exact dependency-receipt SHA-256.

Before npm is invoked, PhiOS reverifies every referenced v0.31 CAS artifact:

- CAS containment under the receipted dependency store;
- regular-file type;
- byte count;
- PhiOS SHA-256;
- original npm lockfile SRI digest.

Each verified artifact is copied to a temporary local `.tgz` path.

npm then receives only local package specs.

Representative command:

```text
npm cache add /LOCAL/VERIFIED/PACKAGE.tgz \
  --cache /ISOLATED/CACHE \
  --offline
```

After all artifacts are added:

```text
npm cache verify --cache /ISOLATED/CACHE --offline
```

No repository build or lifecycle command is executed during cache preparation.

## Cache preparation network claim

The cache-preparation subprocess records:

```text
population_network_control = npm_offline_flag
os_network_namespace_enforced = false
```

That is deliberate.

npm's `--offline` setting is an application-level network control. The current cache preparation
step does not claim an OS-level network namespace.

The later build has the stronger v0.30 kernel namespace boundary.

## Sanitized npm environment

Cache preparation uses a bounded environment containing:

- PATH;
- private HOME;
- private temporary directory;
- isolated npm cache path;
- controlled empty user npmrc;
- npm offline mode;
- audit disabled;
- fund output disabled;
- update notifier disabled.

The host user's normal npm cache is not used.

## npm cache receipt

The npm cache receipt binds:

- receipt UUID/time;
- v0.31 dependency-receipt SHA-256;
- app/repository/commit identity;
- original build-plan SHA-256;
- source-snapshot SHA-256;
- lockfile SHA-256;
- npm executable path/version identity;
- absolute isolated cache path;
- cache-tree SHA-256;
- cache file count;
- cache total bytes;
- dependency artifact count;
- population network control;
- OS network-namespace claim;
- ready status;
- its own canonical SHA-256.

The cache tree digest is computed from sorted records of:

```text
relative path
byte count
SHA-256(file bytes)
```

Symlinks and special files are rejected.

## Offline plan derivation

v0.32 currently accepts only an exact reviewed npm dependency step:

```text
argv = ["npm", "ci"]
requires_network = true
```

That step becomes:

```text
argv = [
  "npm",
  "ci",
  "--offline",
  "--cache",
  "/phios/npm-cache"
]
requires_network = false
```

The derived build plan also removes:

```text
build.network.dependencies
```

It retains the original:

- source snapshot;
- manifest/acquisition identity;
- expected outputs;
- build command;
- required tools;
- process-execution authority;
- workspace-write authority.

## Offline plan wrapper

The v0.32 wrapper binds:

- original build-plan SHA-256;
- npm-cache-receipt SHA-256;
- v0.31 dependency-receipt SHA-256;
- npm cache-tree SHA-256;
- fixed cache mount target;
- complete derived v0.28-compatible build plan.

The wrapper receives its own canonical SHA-256.

Execution requires approval of that exact wrapper digest.

## Sandbox extension

v0.32 extends the v0.30 Bubblewrap runner with optional declared auxiliary mounts and environment.

Auxiliary mount targets:

- must be absolute;
- must live under `/phios/...`;
- must use unique targets;
- must reference existing non-symlink host paths.

Auxiliary environment keys:

- are bounded;
- may not override v0.30 reserved sandbox environment keys.

When v0.32 supplies a writable npm cache mount, v0.30 control evidence correctly changes:

```text
workspace_only_writable_mount = false
```

The source workspace remains the only writable application source mount; the npm cache is a
separately declared writable auxiliary mount.

## Immutable evidence cache vs writable execution cache

The receipted npm cache is never mounted writable into the build.

Immediately before execution PhiOS:

1. reverifies the receipted cache-tree SHA-256 and totals;
2. copies the cache to a fresh execution-specific working cache;
3. hashes the copy;
4. requires the copy to match the receipted cache;
5. mounts only the copy read/write at `/phios/npm-cache`.

npm is therefore free to update cache metadata during `npm ci` without mutating the evidence cache.

## Build-time network denial

The derived plan is executed through v0.30 using:

```text
BuildSandboxPolicy(network_mode="deny")
```

The sandbox receives:

```text
/phios/npm-cache   writable execution cache copy
/workspace         writable execution source
```

and the environment contains:

```text
NPM_CONFIG_CACHE=/phios/npm-cache
NPM_CONFIG_OFFLINE=true
NPM_CONFIG_AUDIT=false
NPM_CONFIG_FUND=false
NPM_CONFIG_UPDATE_NOTIFIER=false
```

Bubblewrap explicitly requests a separate network namespace.

If npm cannot satisfy a dependency from the provided cache, offline installation fails instead of
falling back to the network.

## Receipt stack

A successful v0.32 execution now has four evidence layers:

1. v0.31 dependency receipt;
2. v0.32 npm cache receipt;
3. v0.29 build execution + v0.30 sandbox receipts;
4. v0.32 offline build receipt.

The final v0.32 receipt binds:

- offline-plan SHA-256;
- original build-plan SHA-256;
- derived build-plan SHA-256;
- npm-cache-receipt SHA-256;
- cache-tree SHA-256;
- cache mount target;
- build-execution receipt SHA-256;
- sandbox receipt SHA-256;
- network mode;
- explicit network-namespace-enforced evidence;
- build status.

## Explicit non-capabilities

v0.32 does not:

- publish packages;
- install completed apps into the PhiOS app catalog;
- grant runtime permissions;
- launch an installed app;
- support pnpm/yarn/bun offline adapters;
- guarantee cross-version npm cache compatibility;
- claim cache preparation itself has OS-level network isolation;
- mutate the original v0.28 build plan;
- treat a derived plan as approved merely because its parent plan was approved.

## Planned next rung

v0.33 should introduce a **Build Artifact Package / Install Contract**.

That rung should take only successful receipted build artifacts and define:

- package identity;
- package manifest;
- artifact-set digest;
- installation root;
- atomic install;
- install receipt;
- app-registry binding;
- uninstall boundary;
- no launch authority yet.

That begins the transition from “we can build a public repo safely” to “PhiOS can install a built app
as an actual governed application.”
