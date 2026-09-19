# PhiOS App Platform v0.29

PhiOS App Platform v0.29 adds the **Build Execution Contract**.

v0.28 produces a deterministic reviewed build plan. v0.29 can execute only an explicitly approved
plan against the exact approved source snapshot.

## Operator flow

```text
reviewed build plan
       +
v0.27 acquisition receipt
       ↓
approve exact plan SHA-256
       ↓
approve exact source snapshot SHA-256
       ↓
approve every requested build permission
       ↓
recompute source snapshot
       ↓
copy source into isolated working copy
       ↓
verify required tools
       ↓
execute exact reviewed argv, shell=False
       ↓
hash expected artifacts
       ↓
build execution receipt
```

## Command

```bash
phi-app execute-build build-plan.json acquisition-receipt.json \
  --approve-plan-sha EXACT_PLAN_SHA256 \
  --approve-source-sha EXACT_SOURCE_SNAPSHOT_SHA256 \
  --allow-build-permission build.network.dependencies \
  --allow-build-permission build.process.execute \
  --allow-build-permission build.workspace.write
```

The permission set must exactly match the reviewed plan. Missing or extra approvals fail closed.

Static no-build plans normally request no build permissions and can omit the permission flags.

## Important containment boundary

v0.29 executes the reviewed process inside a separate working copy of the acquired source.

It does **not** claim to provide an OS security sandbox.

The receipt states:

```text
isolation_mode = isolated_working_copy_no_os_sandbox
network_sandbox_enforced = false
```

A process that has been explicitly approved to execute can still use capabilities exposed by the
host operating system and user account. Strong filesystem, process, syscall, and network
containment belongs to a later sandbox rung.

## Receipts

Execution receipts bind:

- exact plan SHA-256;
- exact source snapshot SHA-256;
- exact acquisition tree SHA-256;
- approved build permissions;
- required tool identities and versions;
- exact executed argv;
- exit code / timeout / duration;
- stdout and stderr byte counts and SHA-256 digests;
- produced artifact paths, byte counts, and SHA-256 digests;
- one canonical artifact-set digest;
- execution workspace;
- final status.

Raw build stdout/stderr content is not persisted by the v0.29 receipt.

See `docs/PHIOS_APP_PLATFORM_V0.29_BUILD_EXECUTION.md`.
