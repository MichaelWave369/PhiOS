# PhiOS App Platform v0.54 — Governed Toolchain Runtime Boundary

## Status

Alpha contract.

New schemas:

- `phios.oci_runtime_adapter_identity.v0.1`
- `phios.oci_runtime_control_evidence.v0.1`
- `phios.toolchain_runtime_request.v0.1`
- `phios.toolchain_runtime_receipt.v0.1`

Consumes:

- v0.28 build plans and exact source snapshots;
- v0.29 build execution receipts;
- v0.30 sandbox policy;
- v0.51 reviewed toolchain capsules;
- v0.52 verified capsule acquisition receipts;
- v0.53 toolchain attestations and sandbox plans.

## Purpose

v0.53 can establish that a toolchain was reviewed and can produce a deterministic
network-denied sandbox plan.

v0.54 defines the execution boundary between that reviewed plan and an OCI runtime
adapter.

The central rule is:

> An exact execution approval is consumed by one toolchain build attempt. The resulting receipt is not reusable execution authority.

## Runtime request

A v0.54 runtime request binds:

- exact v0.28 build plan;
- exact source acquisition binding;
- exact v0.51 capsule;
- exact v0.52 capsule acquisition receipt;
- exact v0.53 attestation;
- exact v0.53 sandbox plan;
- approval of the exact sandbox-plan SHA-256;
- approval of the exact attestation SHA-256;
- approval of the exact source-snapshot SHA-256;
- exact reviewed build permissions;
- `execution_scope = single_toolchain_build`.

Construction reconstructs the v0.53 attestation and sandbox plan from the earlier
lineage.

Execution is refused unless the v0.53 plan is:

```text
ready_for_runtime_adapter_review
```

and every build step is already network-free.

A `dependency_staging_required` plan cannot cross the v0.54 execution boundary.

## OCI runtime adapter protocol

v0.54 introduces an injectable `OciRuntimeBuildRunner` boundary.

An adapter must bind itself to:

- exact capsule artifact SHA-256;
- exact v0.52 capsule storage path;
- exact v0.53 sandbox-plan SHA-256;
- exact v0.30 sandbox-policy SHA-256.

It must provide:

- a canonical runtime-adapter identity;
- strict runtime control evidence;
- a fresh in-runtime tool observation set;
- the existing v0.29 build-runner probe/run interface.

There is deliberately no default production OCI backend in v0.54.

That prevents the presence of Docker, Podman, containerd or another engine on the host
from silently becoming PhiOS execution authority.

A production backend should be added only after its command construction, image
materialization, rootless behavior and host isolation are independently qualified.

## Mandatory runtime controls

Every accepted adapter must attest all of the following:

```text
rootfs_read_only = true
workspace_bind_read_write = true
network_namespace_enforced = true
host_network_inherited = false
host_control_plane_mounted = false
privileged_mode = false
capabilities_dropped = true
no_new_privileges = true
shell_invocation = false
```

These are contract requirements, not optional hardening recommendations.

## Pre-execution revalidation

Immediately before adapter preflight, PhiOS re-reads the v0.52 capsule-store artifact
and requires:

- regular file;
- no symlink;
- exact receipted byte count;
- exact reviewed SHA-256.

This prevents a previously verified capsule from being replaced between v0.52 and
execution.

## In-runtime attestation recheck

The runtime adapter must produce a fresh `ToolProbeObservation` set from inside its
runtime boundary.

PhiOS requires that canonical observation set to exactly match the reviewed v0.53
observation set, including:

- tool names;
- fixed probe argv;
- normalized versions;
- subject locators;
- subject SHA-256 values;
- probe-output SHA-256 values.

PhiOS then reconstructs an additional v0.53 attestation using the runtime adapter's own
identity/version as the inspector identity.

The build executor's ordinary v0.29 tool probes are also compared against the fresh
runtime observations before v0.54 emits its final receipt.

## Build execution

After all lineage, artifact, runtime-control and attestation checks pass, v0.54 delegates
the exact build plan to the existing v0.29 `BuildExecutionService` through the injected
OCI adapter.

The adapter must preserve:

```text
network_sandbox_enforced = true
```

The existing build executor retains:

- exact source-copy verification;
- reviewed argv;
- no shell execution;
- bounded timeouts;
- tool identities;
- step receipts;
- artifact hashing;
- build execution receipt.

## Runtime receipt

The v0.54 receipt binds:

- full source/build/capsule lineage;
- exact v0.53 sandbox plan;
- exact capsule artifact;
- runtime observation-set SHA-256;
- runtime recheck attestation SHA-256;
- OCI adapter identity;
- runtime control evidence;
- underlying v0.29 build-execution receipt SHA-256;
- resulting build status.

The receipt fixes:

```text
execution_approval_consumed = true
reusable_execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

A successful v0.54 build remains subject to the existing artifact/install gates.

## Explicit non-capabilities

v0.54 does not ship or select a production Docker/Podman/containerd backend.

It does not:

- auto-install an OCI engine;
- treat an engine on PATH as authorized;
- allow host networking;
- allow privileged containers;
- allow host control-plane mounts;
- allow shell-string execution;
- execute plans still awaiting dependency staging;
- grant app install or launch authority;
- change release or publication authority.

## Next boundary

v0.55 should implement and qualify the first concrete rootless OCI backend, likely
Podman, against the v0.54 adapter protocol.

That backend must prove its exact command surface and controls before it becomes a
selectable runtime capability.

The governing distinction remains:

```text
OCI engine installed
!= OCI engine authorized
```
