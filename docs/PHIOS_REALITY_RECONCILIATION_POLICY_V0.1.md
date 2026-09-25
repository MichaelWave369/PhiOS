# PhiOS Reality Reconciliation Policy v0.1

## Status

Runtime integration candidate.

## Core law

```text
OBSERVATION != RECONCILIATION
RECONCILIATION POLICY != AUTHORITY
RETRY SAFE != RETRY AUTHORIZED
```

PhiOS v0.1 already records an `outcome_unknown` execution and can create an
evidence-backed reconciliation receipt. This rung binds that reconciliation to
the exact capability contract, declared effect scope, Reality Verification claim
semantics, and canonical evidence identity.

## Problem

Without an explicit policy binding, an uncertain action could theoretically be
reconciled using evidence that is real but irrelevant.

A filesystem mutation, network control-plane operation, HTTP state change, and
display-control action do not necessarily share the same valid observation
method.

A hash proves identity. It does not prove relevance.

## RealityReconciliationPolicy

A policy binds:

- policy ID;
- exact capability ID;
- exact capability version;
- canonical declared effect scope;
- allowed Reality claim kinds;
- how a fully contradicted intended postcondition is interpreted.

The policy carries zero operational, action, or execution authority.

The capability contract is rechecked at reconciliation time. Version or effect
scope drift fails closed.

## Contradiction semantics

A supported intended postcondition means:

```text
effect_confirmed
```

A mixed, unresolved, or blocked Reality result means:

```text
inconclusive
```

A fully contradicted intended postcondition is capability-specific. The policy
must explicitly choose one of:

```text
no_effect_confirmed
inconclusive
```

The safer default is `inconclusive`.

This matters because observing that the intended final state is absent does not
always prove that no partial side effect occurred.

## Evidence binding

Reality Verification currently records native content-addressed evidence URIs
such as:

```text
evidence:sha256:<content>
```

The reconciliation layer requires canonical `EvidenceRef` objects whose
content identities exactly cover the Reality receipt's `evidence_used` set.

Therefore:

```text
REALITY EVIDENCE URI != CANONICAL PROVENANCE BY ITSELF
```

No omitted evidence and no unrelated extra evidence are accepted.

## RealityBoundReconciliationReceipt

The wrapper receipt binds:

- exact policy digest;
- capability ID/version;
- exact effect scope;
- Reality receipt ID and deterministic digest;
- normalized claim IDs, kinds, and verdicts;
- the complete underlying ExecutionReconciliationReceipt.

The wrapper also carries zero authority.

## Runtime loop

```text
OUTCOME_UNKNOWN
      ↓
exact capability contract
      ↓
RealityReconciliationPolicy
      ↓
permitted Reality claim kind/provider
      ↓
RealityVerificationResult
      ↓
canonical EvidenceRef coverage
      ↓
RealityBoundReconciliationReceipt
      ↓
effect_confirmed / no_effect_confirmed / inconclusive
```

Even when the result is `no_effect_confirmed` and `retry_safe = true`, a new
action still requires the ordinary PhiOS authority path.

## Scope

v0.1 intentionally does not:

- infer a reconciliation policy from a capability name;
- treat arbitrary evidence as relevant;
- grant retry authority;
- automatically issue a new ActionLease;
- automatically construct capability-specific postcondition claims;
- weaken Reality Verification provider permissions;
- treat contradiction as no-effect unless the capability policy says so.

The next rung can add a governed policy registry and capability-specific
postcondition builders for concrete domains such as filesystem, local service,
network interface, and external control-plane operations.
