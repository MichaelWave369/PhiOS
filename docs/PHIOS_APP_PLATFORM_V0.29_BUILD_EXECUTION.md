# PhiOS App Platform v0.29 — Build Execution Contract

## Status

Alpha contract.

Schemas:

- `phios.build_execution_request.v0.1`
- `phios.build_execution_receipt.v0.1`

## Purpose

v0.29 is the first App Platform rung that may execute build processes.

Its job is deliberately narrow:

> Execute exactly the reviewed v0.28 argv against exactly the reviewed source bytes, only after the
> operator explicitly approves the reviewed build authority, then record what happened.

## Required inputs

Execution requires:

1. one valid v0.28 build plan;
2. the v0.27 acquisition receipt used by that plan;
3. explicit approval of the exact `plan_sha256`;
4. explicit approval of the exact `source_snapshot_sha256`;
5. an explicit permission set exactly equal to the plan's requested build permissions.

The executor verifies that plan and acquisition receipt agree on:

- app ID;
- repository URL;
- exact commit SHA;
- manifest SHA-256;
- v0.27 acquisition tree SHA-256;
- source file count;
- source total byte count.

A `review_required` plan is not executable.

## Permission contract

The permission approval is exact-set based.

For example, when a reviewed plan requests:

```text
build.network.dependencies
build.process.execute
build.workspace.write
```

the operator must approve exactly those three permissions.

Approving only two fails closed.

Adding a fourth permission also fails closed.

Authority does not widen accidentally during execution.

## Pre-execution source verification

Immediately before creating the execution copy, v0.29 recomputes the v0.28
`source_snapshot_sha256` from the acquired source workspace.

It also rechecks source file count and total bytes.

Any byte drift after review blocks execution before tool probes or build processes are launched.

## Isolated working copy

The approved source is copied into a unique execution directory:

```text
EXECUTION_ROOT/
  APP_ID/
    PLAN_SHA256/
      EXECUTION_ID/
        source/
        .phios-env/
```

The copied source is snapshotted again before execution.

A copy mismatch fails closed.

Build steps run only inside the execution copy. The v0.27 acquired source is not used as the
process working directory.

Receipts are forbidden inside either source tree.

## Process invocation

v0.29 invokes reviewed commands as explicit argv arrays with:

```text
shell = false
stdin = null / DEVNULL
```

The executor does not translate the reviewed argv into a shell string.

A bounded clean environment is supplied rather than the complete parent process environment.

The build environment receives a separate HOME and temporary directory beneath the execution
workspace.

## Tool verification

Before build steps, v0.29 probes only a bounded known tool family used by v0.28 plans:

- npm;
- Node;
- pnpm;
- Yarn;
- Bun;
- Python;
- Python build module;
- Cargo;
- rustc;
- Go.

Tool probes are bounded process executions.

The receipt records the resolved executable path, bounded version text, and a digest of the probe
output.

## Output capture

Build stdout and stderr are continuously drained to avoid ordinary pipe deadlocks.

v0.29 receipts persist:

- byte count;
- SHA-256 digest.

Raw build stdout/stderr content is not persisted by default.

This reduces accidental persistence of tokens, credentials, or other sensitive build output while
still giving the execution receipt a deterministic output identity.

## Timeouts

Each build step has a bounded timeout.

The CLI default is 900 seconds per step.

The service accepts 1–3600 seconds.

A timeout marks the execution failed and stops later build steps.

## Artifact verification

Only v0.28 `expected_outputs` are promoted into v0.29 artifact evidence.

Expected file, directory, and bounded glob outputs are resolved beneath the execution source.

Artifact collection rejects:

- missing expected outputs;
- symlinks;
- special files;
- oversized individual artifacts;
- excessive artifact counts;
- excessive total artifact bytes.

Each artifact records:

- relative path;
- byte count;
- SHA-256.

The sorted canonical artifact records produce `artifact_set_sha256`.

A successful process sequence with a missing expected artifact becomes a failed execution receipt.

## Failure receipts

A build step returning nonzero or timing out produces a failed execution receipt.

Later steps are not executed.

Artifact promotion does not occur after a failed step.

Pre-execution authorization or source-integrity failures are blocked before process launch and are
reported as blocked errors rather than successful-looking execution receipts.

## Containment claim

The execution working copy is **isolation**, not a security sandbox.

v0.29 explicitly records:

```text
isolation_mode = isolated_working_copy_no_os_sandbox
network_sandbox_enforced = false
```

The current executor does not claim to enforce:

- filesystem namespace isolation;
- syscall filtering;
- process-tree confinement;
- outbound host/domain restrictions;
- container/VM isolation;
- CPU or memory quotas.

Those require an OS-level sandbox/container contract and must not be inferred from v0.29.

## Receipt identity

The canonical receipt body is SHA-256 hashed and emitted as `receipt_sha256`.

The receipt includes:

- execution UUID and timestamp;
- app/repository/commit identity;
- plan/source/acquisition digests;
- exact approved permissions;
- isolation claim;
- tool identities;
- step receipts;
- artifact receipts;
- artifact-set digest;
- final status and bounded failure reason.

## Explicit non-capabilities

v0.29 does not:

- grant permissions beyond explicit approval;
- modify the acquired source workspace intentionally;
- invoke an interactive shell;
- claim host-level sandboxing;
- install/register the produced app into PhiOS;
- launch the produced app;
- promote build success into runtime trust;
- auto-update an app;
- provide rollback.

## Planned next rung

v0.30 should add a **Build Sandbox / Containment Contract** before broad use of arbitrary third-party
builds.

That rung should define enforceable operating-system controls for:

- network denial / allowlisting;
- filesystem visibility;
- process-tree termination;
- CPU / memory / wall-clock budgets;
- temporary directories;
- environment-variable policy;
- sandbox receipts.

Only after enforceable containment should PhiOS treat arbitrary third-party build execution as a
general application-platform capability.
