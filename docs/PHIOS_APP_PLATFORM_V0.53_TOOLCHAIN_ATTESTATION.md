# PhiOS App Platform v0.53 — Toolchain Attestation and Sandbox Plan

## Status

Alpha contract.

New schemas:

- `phios.toolchain_attestation.v0.1`
- `phios.toolchain_sandbox_plan.v0.1`

Consumes:

- v0.28 build plans;
- v0.30 sandbox policy;
- v0.51 toolchain requirements/capsules/bindings;
- v0.52 capsule acquisition receipts.

## Purpose

v0.52 proves that the exact opaque capsule artifact bytes are available locally.

v0.53 adds two bounded transitions:

1. attest that the reviewed tool components were observed at the reviewed versions;
2. construct a deterministic, network-denied sandbox plan bound to that attestation.

The central rule is:

> Attested tools and a complete sandbox plan are still not execution authority.

## Tool probe observations

A v0.53 observation records:

- tool name;
- exact probe argv;
- normalized observed version;
- bounded subject locator;
- subject SHA-256;
- probe-output SHA-256.

The accepted probe contract is fixed for the first four capsule families:

| Tool | Probe |
| --- | --- |
| node | `node --version` |
| npm | `npm --version` |
| python | `python --version` |
| python-build | `python -m build --version` |
| cargo | `cargo --version` |
| rustc | `rustc --version` |
| go | `go version` |

The observation producer is intentionally outside this rung. v0.53 validates and binds the evidence; it does not yet unpack OCI layers or launch an OCI runtime.

## Attestation

`attest_toolchain()` reconstructs the v0.51 requirement and binding from the exact v0.28 build plan and reviewed capsule.

It then requires the v0.52 receipt to match:

- app identity;
- exact source commit;
- build-plan SHA-256;
- requirement SHA-256;
- capsule SHA-256;
- binding SHA-256;
- reviewed artifact SHA-256;
- `verified_available` status.

The observed tool-name set must exactly equal the capsule's reviewed tool set.

Every normalized observed version must exactly equal the corresponding reviewed capsule version.

A successful attestation binds:

- the complete source/build lineage;
- the exact capsule/acquisition lineage;
- inspector ID and version;
- every tool observation;
- a canonical attestation SHA-256;
- `status = attested_for_review`.

## Sandbox plan

`plan_toolchain_sandbox()` binds:

- exact build plan;
- exact v0.52 acquisition receipt;
- exact reviewed capsule;
- exact v0.53 attestation;
- existing v0.30 `BuildSandboxPolicy`;
- exact build steps;
- capsule storage path and artifact digest.

v0.53 permits only:

```text
network_mode = deny
```

If any original v0.28 build step still requires network access, the plan is classified:

```text
dependency_staging_required
```

That preserves the existing dependency-broker/offline-build boundary.

If every build step is already network-free, the status is:

```text
ready_for_runtime_adapter_review
```

Neither status authorizes execution.

## Fixed authority fields

Every attestation and sandbox plan fixes:

```text
execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

The sandbox plan also fixes:

```text
runtime_adapter_required = true
```

because PhiOS does not yet have a v0.53 OCI runtime adapter that can expose the attested toolchain to the v0.30 build sandbox.

Therefore:

```text
capsule bytes verified
!= tools attested

tools attested
!= runtime adapter exists

runtime adapter exists
!= execution authorized

execution succeeds
!= install authority
```

## Fail-closed behavior

v0.53 rejects:

- unknown tool probes;
- altered probe argv;
- malformed subject locators;
- malformed evidence digests;
- duplicate observations;
- missing or extra observed tools;
- observed-version mismatch;
- build-plan/acquisition identity mismatch;
- requirement/capsule/binding mismatch;
- unverified capsule availability;
- attestation/acquisition mismatch;
- non-denied sandbox network policy;
- unknown attestation or plan fields;
- digest tampering;
- authority fields changed from false.

## Explicit non-capabilities

v0.53 does not:

- unpack OCI artifacts;
- run a container runtime;
- execute the version probes itself;
- grant trust merely because an inspector emitted evidence;
- execute build steps;
- provide dependency-network authority;
- install or launch an app;
- change release or publication authority.

The inspector identity and version are evidence fields, not trust roots.

## Next boundary

v0.54 should introduce a governed OCI runtime adapter that can materialize an exact v0.52 artifact, re-check the v0.53 attestation inside the runtime boundary, and execute an explicitly approved network-denied sandbox plan.

That rung must preserve:

```text
runtime adapter available
!= execution authorized
```
