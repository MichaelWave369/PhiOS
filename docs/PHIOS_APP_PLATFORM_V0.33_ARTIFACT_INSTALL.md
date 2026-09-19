# PhiOS App Platform v0.33 — Build Artifact Package / Install Contract

## Status

Alpha contract.

Schemas:

- `phios.build_package_plan.v0.1`
- `phios.build_package_plan_review.v0.1`
- `phios.app_install_receipt.v0.1`
- `phios.app_uninstall_receipt.v0.1`

## Purpose

v0.33 turns a successful, receipted build into a governed filesystem installation without granting
execution authority.

The install path is intentionally separate from source acquisition and build workspaces.

## Required provenance

Package planning requires:

- one valid app manifest;
- that exact manifest already present in the v0.25 AppRegistry;
- one successful v0.29 build execution receipt;
- one successful v0.32 npm offline-build receipt.

The offline-build receipt must bind the supplied build-execution receipt.

The successful build must prove:

- build status is `success`;
- no failure reason;
- network sandbox enforcement was active;
- artifact list is non-empty;
- artifact list is sorted and unique;
- artifact-set SHA-256 matches the canonical artifact records.

The v0.32 receipt must prove:

- build status is `success`;
- `network_mode=deny`;
- network namespace enforcement is true;
- app/commit identity matches;
- derived build-plan SHA-256 matches the execution receipt;
- build-execution receipt SHA-256 matches exactly.

## Registry binding

The AppRegistry remains an identity registry.

v0.33 does not redefine registration as installation.

A deterministic registry snapshot SHA-256 is recorded in the package plan.

At install time PhiOS requires:

- the current registry snapshot SHA-256 to still match the reviewed package plan;
- the registered manifest SHA-256 for the target app to still match.

Any registry change after package review therefore invalidates that install approval.

This is conservative by design.

## Package plan

The package plan binds:

- app ID;
- app version;
- manifest SHA-256;
- registry snapshot SHA-256;
- repository URL;
- exact commit SHA;
- build-plan SHA-256;
- build-execution receipt SHA-256;
- v0.32 offline-build receipt SHA-256;
- artifact-set SHA-256;
- complete artifact list;
- deterministic relative install path;
- `launch_authority=false`.

The plan receives its own canonical SHA-256.

## Artifact set

Each package artifact records:

- relative POSIX path;
- byte count;
- SHA-256.

The artifact-set digest is:

```text
SHA-256(
  sorted(
    path + NUL +
    byte_count + NUL +
    file_sha256 + NEWLINE
  )
)
```

Only the receipted artifact list is installable.

The complete execution workspace is not a package source.

## Source artifact re-verification

Immediately before installation PhiOS reverifies every artifact in the execution workspace.

It checks:

- safe relative path;
- containment beneath the execution workspace;
- no symlink at the artifact path;
- regular-file type;
- byte count;
- SHA-256.

The artifact is read again during the actual install copy and its byte count and SHA-256 are checked
again before those bytes are written to staging.

This reduces the gap between provenance verification and copy.

## Install layout

Default root:

```text
~/.phios/apps/installed/
```

A package installs beneath a deterministic relative path:

```text
APP_ID/
  APP_VERSION/
    ARTIFACT_SET_PREFIX/
      payload/
        ... receipted build artifacts ...
      .phios/
        package-plan.json
        manifest.json
```

The `.phios` metadata is outside the payload digest.

The installed payload digest therefore remains exactly the build artifact-set digest.

## Atomic installation

PhiOS:

1. creates staging under the configured install root;
2. copies only receipted artifacts into `payload/`;
3. hashes the complete staged payload;
4. requires exact equality with the reviewed artifact-set SHA-256;
5. writes package/manifest metadata;
6. moves the complete staging directory to the final destination atomically;
7. rehashes the final payload;
8. writes the install receipt.

An existing final install path is never overwritten.

If installation fails after promotion but before a valid install receipt is persisted, the new
install directory is removed.

## Install receipt

The receipt binds:

- receipt UUID/time;
- app ID/version;
- package-plan SHA-256;
- manifest SHA-256;
- registry snapshot SHA-256;
- build-plan SHA-256;
- build-execution receipt SHA-256;
- v0.32 offline-build receipt SHA-256;
- build artifact-set SHA-256;
- installed payload SHA-256;
- artifact count;
- total bytes;
- absolute install path;
- `launch_authority=false`;
- `status=installed`.

The receipt receives its own canonical SHA-256.

## Launch boundary

v0.33 does not inspect, select, authorize, or execute a runtime entrypoint.

An installed app is inert application material.

```text
installed app
    ≠ runtime grant
    ≠ launch approval
    ≠ running process
```

Runtime authority belongs to a later contract.

## Uninstall boundary

Uninstall requires:

- one valid install receipt;
- explicit approval of that exact install-receipt SHA-256;
- the receipted install path to remain beneath the configured install root;
- the current installed payload SHA-256 to still match the install receipt.

If the payload changed after installation, uninstall fails closed rather than deleting modified
content under stale authority.

A successful uninstall removes only the receipted install directory and emits an uninstall receipt.

## Explicit non-capabilities

v0.33 does not:

- launch the app;
- grant runtime permissions;
- infer a runtime adapter;
- create desktop shortcuts;
- start services;
- modify system PATH;
- install OS packages;
- install dependency caches;
- copy the full source workspace;
- overwrite an existing install;
- silently update an installed app.

## Planned next rung

v0.34 should introduce the **Installed App Runtime Contract**.

That rung should resolve an installed package to a bounded runtime adapter and separately review:

- runtime kind;
- installed entrypoint mapping;
- requested runtime permissions;
- environment;
- filesystem mounts;
- network policy;
- process limits;
- launch-plan SHA-256;
- explicit launch approval;
- runtime receipt.

Only then should an installed PhiOS app become runnable.
