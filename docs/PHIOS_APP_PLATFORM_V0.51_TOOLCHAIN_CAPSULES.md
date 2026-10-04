# PhiOS App Platform v0.51 — Toolchain Capsule Contract

## Status

Alpha contract.

New schemas:

- `phios.toolchain_requirement.v0.1`
- `phios.toolchain_capsule.v0.1`
- `phios.toolchain_binding.v0.1`

## Purpose

v0.28 can already identify several build families and the tools they require. v0.29 can probe and execute host tools. That is useful, but it leaves a gap between:

```text
this build needs Python / Node / Rust / Go
```

and:

```text
these exact toolchain bytes are the environment reviewed for this build
```

v0.51 introduces a declarative, digest-bound toolchain-capsule contract.

The central rule is:

> A toolchain can be compatible with a build without having authority to execute it.

## Supported v0.51 families

The first contract recognizes exactly four Linux x86_64 families:

| Family | Required tools |
| --- | --- |
| `node_npm` | `node`, `npm` |
| `python_pep517` | `python`, `python-build` |
| `rust_cargo` | `cargo`, `rustc` |
| `go_module` | `go` |

Current pnpm, Yarn and Bun build plans remain valid v0.28 observations, but v0.51 classifies them as `unsupported_toolchain`. Future adapters must get their own explicit contract rather than silently borrowing Node/npm semantics.

Static-web source that requires no build produces `no_capsule_required`.

## Requirement derivation

`derive_toolchain_requirement()` consumes an exact v0.28 `BuildPlan` and binds:

- app identity;
- exact commit;
- canonical build-plan SHA-256;
- strategy;
- required tools;
- one supported family when deterministically recognized;
- status.

Possible statuses are:

- `capsule_required`
- `no_capsule_required`
- `unsupported_toolchain`

Every requirement fixes:

```text
execution_authority = false
```

A requirement is evidence about what a build needs. It is not permission to obtain or run a toolchain.

## Capsule contract

A v0.51 capsule declares:

- bounded capsule ID;
- toolchain family;
- platform = `linux_x86_64`;
- artifact kind = `oci_image`;
- immutable artifact SHA-256;
- artifact reference;
- exact tool names and version strings;
- canonical capsule SHA-256.

The family fixes the exact tool-name set. A Node/npm capsule cannot omit npm, add pnpm, or masquerade as a Rust capsule.

The artifact reference is descriptive. The artifact SHA-256 is the immutable identity field.

v0.51 does not download, inspect, start or trust the referenced OCI artifact. Artifact acquisition and verification are separate future boundaries.

## Fixed zero-authority fields

Every capsule and every successful binding fixes:

```text
execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

These fields are validated, hashed, and fail closed if changed.

Therefore:

```text
capsule exists
!= capsule acquired

capsule acquired
!= capsule verified

capsule verified
!= build may execute

capsule matches requirement
!= build may execute

build may execute
!= network authority

build succeeds
!= install authority
```

## Binding

`bind_toolchain_capsule()` accepts only:

- a `capsule_required` requirement;
- an exact matching family;
- an exact matching tool set.

A successful binding records:

- app/commit/build-plan identity;
- requirement SHA-256;
- capsule SHA-256;
- family;
- status = `compatible_for_review`;
- fixed zero-authority fields.

The binding is review evidence only.

## Fail-closed behavior

v0.51 rejects:

- unknown schema fields;
- malformed digests;
- duplicate tools;
- missing or extra family tools;
- unsupported platform or artifact kind;
- non-false authority fields;
- digest tampering;
- capsule binding for a no-build or unsupported requirement;
- family mismatch;
- tool-set mismatch.

## Explicit non-capabilities

v0.51 does not:

- pull OCI images;
- invoke Docker, Podman, Bubblewrap or another container runtime;
- execute Node, npm, Python, Cargo, Rust or Go;
- install a compiler into the base PhiOS image;
- grant network access;
- grant host filesystem writes;
- replace v0.30 sandbox approval;
- replace dependency-broker approval;
- install or launch an application;
- infer trust from a version string;
- make a release-ready claim.

## Why capsules instead of a giant ISO

The base operating system should not need every compiler and package manager merely because a public repository might use one.

The intended future flow is:

```text
GitHub intake
  -> exact source acquisition
  -> build plan
  -> toolchain requirement
  -> reviewed capsule binding
  -> verified capsule acquisition
  -> dependency broker
  -> network-denied sandbox execution
  -> artifact verification
  -> governed install
```

This keeps the base image smaller and preserves the PhiOS rule that capability and authority are separate.

## Next boundary

v0.52 should introduce governed capsule acquisition and verification.

That rung should prove that the locally available capsule bytes match the exact reviewed v0.51 artifact identity before any build executor can consume them.

It must still preserve:

```text
verified capsule
!= execution authority
```
