# PhiOS App Platform v0.55 — Rootless Podman OCI Backend

## Status

Alpha backend.

v0.55 implements the first concrete OCI runtime adapter for the v0.54 governed
toolchain-runtime boundary.

The backend is:

```text
phios.podman-rootless / 0.1.0
```

The central rule remains:

> Podman being installed is not authority for PhiOS to use Podman.

## Scope

The v0.55 backend consumes the exact already-reviewed lineage:

- v0.51 capsule;
- v0.52 verified capsule acquisition;
- v0.53 attestation and network-denied sandbox plan;
- v0.54 one-use execution approval.

It implements the v0.54 `OciRuntimeBuildRunner` protocol.

No automatic backend selection is added in this rung.

An operator or higher governed layer must still explicitly construct the Podman adapter
for the exact approved runtime request.

## Rootless qualification

The adapter is Linux-only and refuses to preflight when the PhiOS host process is
running as UID 0.

It also requires `podman info --format json` to report:

```text
host.security.rootless = true
```

A host Podman binary therefore cannot enter the runtime path merely because it exists.

## Isolated image store

Each adapter instance receives an explicit fresh `state_root`.

v0.55 refuses a non-empty state root and uses an isolated Podman store:

```text
--root STATE/graphroot
--runroot STATE/runroot
--storage-driver=vfs
```

The exact v0.52 capsule artifact is loaded with `podman load --input`.

After loading, the isolated store must contain exactly one unique full image ID.

The image ID is then used for every probe and build command with `--pull=never`.

This prevents a registry lookup or a similarly named host image from silently replacing
the reviewed capsule.

## Container command contract

Every v0.55 container invocation fixes:

```text
--rm
--pull=never
--network=none
--read-only
--read-only-tmpfs=true
--cap-drop=all
--security-opt=no-new-privileges
--pids-limit=256
--userns=keep-id
```

Build execution adds exactly one host bind:

```text
approved execution source -> /workspace (read/write)
```

No PhiOS control-plane path, host home directory, container socket or arbitrary host
path is mounted.

The build working directory is derived from the already-approved source tree and must
remain under `/workspace`.

No shell string is used. Every probe and build step remains an argv vector.

## Runtime observation producer

v0.54 requires a fresh tool observation set from inside the runtime boundary.

v0.55 produces that set itself.

For each reviewed v0.53 tool observation it:

1. requires an absolute subject locator;
2. runs `sha256sum SUBJECT` directly inside the loaded capsule;
3. runs the exact fixed v0.53 probe argv directly inside the capsule;
4. computes the same normalized version and probe-output digest used by the v0.29 build
   execution surface;
5. returns a fresh `ToolProbeObservation`.

The v0.54 service then requires the complete fresh observation set to equal the reviewed
v0.53 observation set before executing the build.

### Current locator limitation

v0.55 requires absolute subject locators.

The v0.53 `python-module:...` locator form remains valid evidence in the abstract
contract but is not executable through this first Podman observer.

A Python capsule intended for v0.55 execution must therefore be attested with an exact
absolute path to the reviewed module artifact.

v0.55 also requires the capsule image to provide `sha256sum` for subject-byte
verification.

These limitations are explicit rather than silently weakening the v0.54 runtime recheck.

## Build probes and steps

The existing v0.29 `BuildExecutionService` still owns:

- exact source-copy verification;
- tool probes;
- step ordering;
- timeouts;
- artifact collection;
- build receipts.

v0.55 merely changes where the reviewed argv executes.

Each v0.29 tool probe runs inside a fresh rootless Podman container against the exact
loaded image and mounted execution source.

Each build step does the same.

Workspace changes persist because only the approved execution source is bind-mounted
read/write.

Container root filesystems remain read-only.

## Fail-closed behavior

v0.55 refuses:

- non-Linux hosts;
- UID 0;
- missing or non-absolute Podman executable;
- symlink/non-regular Podman executable;
- non-rootless Podman info;
- reused/non-empty adapter state;
- failed exact archive load;
- zero or multiple image identities in the isolated store;
- unsupported non-absolute subject locators;
- invalid subject-hash output;
- failed version probes;
- changed build-tool probe argv;
- working-directory escape;
- build steps that still require network access.

## Non-capabilities

v0.55 does not:

- pull from registries;
- log in to registries;
- auto-select Podman;
- expose the Podman socket;
- mount the host home directory;
- run privileged containers;
- inherit host networking;
- support v0.53 `python-module:` observation locators;
- grant install or launch authority;
- change release/publication authority.

## Next boundary

v0.56 should add a governed runtime-backend selector and backend qualification receipt.

The selector should evaluate available qualified adapters but remain advisory until an
operator explicitly authorizes one for the exact v0.54 request.

The governing distinction remains:

```text
backend qualified
!= backend selected
!= execution authorized
```
