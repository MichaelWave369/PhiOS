# PhiOS App Platform v0.31 — Dependency Staging / Network Broker Contract

## Status

Alpha contract.

Schemas:

- `phios.dependency_plan.v0.1`
- `phios.dependency_plan_review.v0.1`
- `phios.dependency_receipt.v0.1`

## Purpose

v0.31 moves dependency network access out of the v0.30 build sandbox.

Its initial job is narrow:

> Read exact npm lockfile artifact identities from already-reviewed source, require explicit
> operator approval of the resulting dependency plan and host set, fetch those artifacts through a
> bounded HTTPS broker, verify lockfile integrity, and stage the exact bytes in a PhiOS
> content-addressed store.

This rung does not grant build authority and does not execute repository code.

## Supported ecosystem

v0.31 supports:

- npm;
- `package-lock.json`;
- `npm-shrinkwrap.json`;
- lockfileVersion 2 or 3.

Other package managers remain unsupported by this broker version and fail closed rather than being
silently approximated.

## Real-world lockfile bound

Earlier App Platform planning treated every build metadata file as a small configuration file and
limited it to 256 KiB.

v0.31 separates lockfiles from ordinary build configuration and allows bounded lockfiles up to
8 MiB.

Ordinary metadata retains the smaller limit.

The whole acquired source remains subject to the existing source-tree bounds.

## Cross-rung binding

A dependency plan binds:

- app ID;
- repository URL;
- exact commit SHA;
- canonical v0.28 build-plan SHA-256;
- v0.28 source-snapshot SHA-256;
- package manager;
- exact lockfile path;
- exact lockfile SHA-256;
- lockfile version;
- exact dependency host set;
- exact artifact list.

Before dependency planning, PhiOS recomputes the current acquired-source snapshot.

Source drift after build-plan review blocks dependency planning.

The currently observed lockfile digest must also match the lockfile digest recorded by the reviewed
build plan.

## Lockfile artifact requirements

Each non-link npm package entry must provide both:

- `resolved`;
- `integrity`.

Entries with incomplete or absent exact artifact evidence fail closed.

Workspace/link entries marked by the lockfile as links do not represent external downloadable
artifacts and are skipped.

## URL contract

External artifact URLs must:

- use HTTPS;
- contain a valid DNS host;
- use the default HTTPS port;
- contain no username/password credentials;
- contain no query string;
- contain no fragment.

The URL is canonicalized before entering the dependency plan.

Query-bearing or credential-bearing URLs are rejected because they can smuggle secrets or
ephemeral authority into what is supposed to be a deterministic reviewed plan.

## SRI contract

Supported lockfile integrity algorithms:

- SHA-512;
- SHA-384;
- SHA-256.

When multiple valid supported SRI tokens exist, PhiOS selects the strongest supported algorithm in
that order.

The broker verifies downloaded bytes against the selected lockfile SRI before staging.

SRI verification and CAS identity are deliberately separate:

- SRI proves the bytes match the reviewed npm lockfile;
- SHA-256 provides the PhiOS content-addressed storage identity.

## Review and approval

`plan-dependencies` produces a deterministic dependency plan.

`review-dependency-plan` exposes:

- dependency-plan SHA-256;
- build-plan SHA-256;
- source-snapshot SHA-256;
- lockfile path;
- lockfile SHA-256;
- artifact count;
- exact host set.

`stage-dependencies` requires:

1. the exact dependency-plan SHA-256;
2. an approved host set exactly equal to the reviewed plan host set.

The host approval contract is exact-set based.

Adding a host is not harmless widening; it changes authority and fails validation.

## HTTPS broker

The built-in broker:

- performs GET only;
- uses a bounded timeout;
- follows at most five redirects;
- revalidates HTTPS and host approval after each redirect;
- rejects response escape to an unapproved host;
- bounds each artifact to 64 MiB;
- bounds the total staging operation to 1 GiB;
- bounds staged artifact count to 4096.

A redirect does not inherit authority merely because the original URL was approved.

The redirect destination must still be part of the exact reviewed/approved host set.

## Content-addressed store

After SRI verification, the broker computes SHA-256 over the downloaded bytes.

Artifacts are stored under:

```text
STORE_ROOT/
  cas/
    sha256/
      XX/
        FULL_SHA256.blob
  .phios-receipts/
    dependency-RECEIPT_ID.json
```

Identical bytes from different lockfile entries share one CAS path.

Existing CAS entries are rehashed and byte-count checked before reuse.

The CAS file itself does not grant build/install authority.

A later rung must bind its use to a valid dependency receipt.

## Dependency receipt

The receipt binds:

- receipt UUID/time;
- app, repository, and commit identity;
- package manager and lockfile version;
- build-plan SHA-256;
- source-snapshot SHA-256;
- dependency-plan SHA-256;
- lockfile path and SHA-256;
- exact approved host set;
- each resolved URL;
- selected SRI algorithm/digest;
- artifact byte count;
- artifact SHA-256;
- CAS path;
- lockfile locations referencing that artifact;
- package version when present;
- total staged bytes;
- dependency-store root.

The receipt receives its own canonical SHA-256 and can be reconstructed with strict field,
host-set, byte-total, CAS-path, and digest validation.

## Shared CAS failure semantics

The content-addressed store is shared infrastructure.

Once bytes have passed lockfile SRI verification and received their SHA-256 CAS identity, PhiOS
does not delete that shared blob merely because a later receipt write fails.

That avoids a rollback race in which one staging process could delete content another concurrent
process has already begun using.

Unreferenced CAS bytes are inert cache material. They do not establish dependency provenance or
build authority.

Only a valid dependency receipt binds CAS content into a later governed workflow.

## Explicit non-capabilities

v0.31 does not:

- execute package-manager install commands;
- execute repository scripts;
- rewrite the v0.28 build plan;
- create `node_modules`;
- synthesize npm's opaque internal cache structure;
- claim that raw CAS blobs are directly consumable by `npm ci --offline`;
- grant build permissions;
- launch an app;
- install an app into PhiOS.

## Why npm cache adaptation is separate

npm's cache is a content-addressable cache with package-manager-specific metadata and internal
behavior.

PhiOS should use npm's supported cache interfaces rather than reverse-engineering or synthesizing
that internal format.

That conversion therefore belongs to a separate adapter boundary.

## Planned next rung

v0.32: **npm Offline Dependency Adapter**.

It should:

1. accept one valid v0.31 dependency receipt;
2. verify every referenced CAS blob again;
3. construct an isolated npm cache using npm's supported cache command/interface;
4. emit an npm-cache receipt;
5. derive a build execution variant whose dependency step is network-free;
6. execute the reviewed project through v0.30 with `network_mode=deny`;
7. use npm's true offline mode so a missing dependency fails instead of reaching the network.

After that, PhiOS will have a complete first path from public npm repo to network-denied sandboxed
build.
