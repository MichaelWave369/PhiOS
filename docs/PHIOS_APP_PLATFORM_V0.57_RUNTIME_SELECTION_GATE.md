# PhiOS App Platform v0.57 — Selected Backend Execution Gate

## Status

Alpha contract.

New schemas:

- `phios.selected_toolchain_runtime_request.v0.1`
- `phios.runtime_selection_execution_receipt.v0.1`

Consumes:

- v0.54 one-use toolchain runtime requests;
- v0.56 backend qualifications;
- v0.56 operator-confirmed backend selection receipts.

## Purpose

v0.56 can qualify a concrete runtime adapter and record the operator's explicit choice.

v0.57 binds that exact choice to the execution path.

The central rule is:

```text
backend qualified
!= backend selected

backend selected
!= execution approved

execution approved for one build
!= permission to swap the backend
```

## Selected runtime request

A v0.57 request contains:

- the exact v0.54 `ToolchainRuntimeRequest`;
- the exact v0.56 backend qualification;
- the exact v0.56 operator selection receipt;
- explicit approval of the canonical selection-receipt SHA-256.

Construction requires the selection to bind the exact:

- qualification;
- sandbox plan;
- capsule;
- attestation;
- adapter ID;
- runtime identity;
- runtime controls.

The existing v0.54 `execution_approval_id` remains the one-use authority that permits
one build attempt.

The v0.56 selection receipt remains selection evidence only.

## Live backend requalification

Immediately before v0.54 execution, `SelectedToolchainRuntimeService` runs the v0.56
qualification function again against the actual injected runner.

The live qualification must be canonically identical to the operator-selected
qualification.

That means the runtime may not silently change:

- adapter ID or version;
- backend implementation;
- backend binary identity;
- platform;
- runtime controls;
- capsule binding;
- sandbox plan;
- sandbox policy.

If any of those change, execution is refused before the v0.54 one-use approval is
consumed.

## Delegated execution

After selection and live requalification pass, v0.57 delegates to the existing v0.54
`ToolchainRuntimeService`.

v0.54 still owns:

- one-use execution approval consumption;
- pre-execution capsule re-hash;
- in-runtime tool re-observation;
- exact build execution;
- runtime receipt generation.

v0.57 does not duplicate those controls.

## Post-execution selection verification

After v0.54 returns, v0.57 verifies that the runtime identity and runtime controls
recorded by the actual execution still equal the operator-selected backend.

A successful v0.57 receipt binds:

- operator selection receipt SHA-256;
- backend qualification SHA-256;
- sandbox/capsule/attestation lineage;
- execution approval ID;
- selected adapter ID;
- actual runtime identity and controls;
- v0.54 runtime receipt SHA-256.

It records:

```text
operator_selection_verified = true
reusable_execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

## Current path

v0.54 remains the lower-level runtime implementation and compatibility boundary.

The current governed App Platform path for backend-selected execution is v0.57:

```text
v0.56 operator selection
  -> v0.57 selection gate
  -> v0.54 one-use execution
```

Callers that need the current governed path should use the v0.57 service.

## Fail-closed behavior

v0.57 rejects:

- stale selection-receipt approval;
- selection/qualification mismatch;
- selection from another sandbox plan;
- selection from another capsule or attestation;
- selected adapter mismatch;
- selected runtime identity mismatch;
- selected runtime controls mismatch;
- live qualification drift before execution;
- execution-time runtime identity drift;
- execution-time runtime control drift;
- authority fields changed from false;
- receipt digest tampering.

## Explicit non-capabilities

v0.57 does not:

- discover or select a backend automatically;
- create an execution approval;
- expand network authority;
- grant install or launch authority;
- change release or publication authority.

## Pivot after v0.57

Once this gate is qualified, the toolchain/runtime spine is sufficiently complete for the
next product-facing phase.

v0.58 should begin the Repo Profiler and compatibility classifier:

```text
GitHub URL
  -> source/license/runtime/build inspection
  -> compatibility class
  -> exact remediation or supported path
```

That work should use the existing governed build/runtime contracts rather than creating
another parallel execution stack.
